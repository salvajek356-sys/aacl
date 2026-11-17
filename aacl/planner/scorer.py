"""Target-pressure scoring (companion §1), replacing Phase 0's static
precision preference as the selector among surviving candidates.

For each candidate, every dimension the workload actually constrained gets
a pressure: the candidate's static estimate divided by the declared budget.
A candidate is judged by its *worst* pressure — how close it comes to
breaking the tightest promise the workload made — and the lowest worst
pressure wins. Candidates whose worst pressures agree within
PRESSURE_EPSILON are tied, and ties break in a fixed order: the workload's
`optimize_for` dimension, then absolute estimated cost, then backend name,
then artifact id. The chain is total and its inputs are deterministic, so
the same request always produces the same plan.

Two honesty rules live here:

- Quality is never a pressure. It is unmeasured until Phase 4, so it
  contributes nothing to any candidate's score. It appears only inside the
  `optimize_for` tie-break, where it names the standing precision
  *preference* — a preference, labeled as one, not a measurement.
- If the workload declared no budgets at all, there is no pressure to
  score. Selection then falls back to that same standing precision
  preference, and the selection's reason says so. (This also keeps the
  default plan the fp64 path, which prove.py's precision comparison uses
  as its reference.)
"""
import math
from dataclasses import dataclass

from ..models.registry import SOURCE_DIGEST, TRANSFORM_VERSION, artifact_id
from .estimates import estimate

REASON = "TARGET_PRESSURE_MINIMAX"
NO_TARGET_REASON = "STATIC_PRECISION_PREFERENCE_NO_TARGETS_DECLARED"
PRESSURE_EPSILON = 1e-9

_DIMENSIONS = ("latency", "memory", "cost")
_BUDGETS = {"latency": "latency_target_ms", "memory": "memory_limit_mb",
            "cost": "cost_budget"}
_ESTIMATES = {"latency": "estimated_latency_ms", "memory": "estimated_memory_mb",
              "cost": "estimated_cost"}


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: object
    estimate: object
    artifact: str
    pressures: tuple  # ((dimension, pressure), ...) over declared budgets only
    worst_pressure: float = None
    binding_dimension: str = None


@dataclass(frozen=True)
class Selection:
    chosen: ScoredCandidate
    scored: tuple
    reason: str


def _pressure(estimated, budget):
    if budget > 0:
        return estimated / budget
    return math.inf if estimated > 0 else 0.0


def _score(spec, profile, candidate):
    est = estimate(candidate, profile, spec)
    artifact = artifact_id(spec.model_id, SOURCE_DIGEST, candidate.precision,
                           TRANSFORM_VERSION, {"backend": candidate.backend})
    pressures = tuple(
        (dim, _pressure(getattr(est, _ESTIMATES[dim]), getattr(spec, _BUDGETS[dim])))
        for dim in _DIMENSIONS if getattr(spec, _BUDGETS[dim]) is not None
    )
    worst = max((p for _, p in pressures), default=None)
    binding = next((dim for dim, p in pressures if p == worst), None)
    return ScoredCandidate(candidate, est, artifact, pressures, worst, binding)


def _optimize_key(spec, scored):
    """The tie-break's first step: the dimension the workload asked to
    optimize. `quality` keys on the standing precision preference — the one
    place a preference is allowed to speak, and it speaks as a preference."""
    if spec.optimize_for == "quality":
        return scored.candidate.preference_rank
    return getattr(scored.estimate, _ESTIMATES[spec.optimize_for])


def select(spec, profile, candidates):
    """The winning candidate, with every survivor's scores attached."""
    scored = tuple(_score(spec, profile, c) for c in candidates)
    declared = [dim for dim in _DIMENSIONS if getattr(spec, _BUDGETS[dim]) is not None]
    if not declared:
        chosen = min(scored, key=lambda s: (s.candidate.preference_rank,
                                            s.candidate.backend, s.artifact))
        return Selection(chosen, scored, NO_TARGET_REASON)
    lowest = min(s.worst_pressure for s in scored)
    tied = [s for s in scored if s.worst_pressure - lowest <= PRESSURE_EPSILON]
    chosen = min(tied, key=lambda s: (_optimize_key(spec, s), s.estimate.estimated_cost,
                                      s.candidate.backend, s.artifact))
    return Selection(chosen, scored, REASON)
