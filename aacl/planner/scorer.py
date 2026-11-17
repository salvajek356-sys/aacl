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

- Quality is a pressure only when it is measured: a named reference the
  registry holds for this model, and a declared tolerance to divide by.
  Anything less — no reference, or a reference with no tolerance — and
  quality contributes no pressure (see the Phase 4 paragraph below).
- If the workload declared no budgets at all, there is no pressure to
  score. Selection then falls back to that same standing precision
  preference, and the selection's reason says so. (This also keeps the
  default plan the fp64 path, which prove.py's precision comparison uses
  as its reference.)

Phase 3 adds the ranking and the reliability memory. The selection now
carries every survivor in decision order (`ranked`) — the plan's fallback
list, computed by applying the same choice repeatedly to whoever remains,
so ranked[0] is always the chosen candidate and the order after it is the
order the executor will try. A candidate the reliability registry has
downgraded (its backend lied about that capability) is deprioritized: its
effective worst pressure carries a full budget of penalty, and it sorts
behind every undowngraded candidate when no budgets are declared. It is
never excluded — a downgraded capability is a last resort, not a ban.

Phase 4 retires the first honesty rule and replaces it with a stricter
one: quality is now *measured* — but only against a named reference, and
only when the workload names one (the spec refuses names that are not
registered eval sets for the model). The measurement (see
optimization/quality.py) is drift against the model's floating-point
artifact on the reference's eval rows. When the workload also declares a
`quality_max_drift` tolerance, quality joins the minimax as a fourth
pressure: measured mean score error divided by the tolerance. When a
reference is declared without a tolerance, drift is carried on every
scored candidate and reported, contributes no pressure, and — when
`optimize_for` asks for quality — ranks tie-breaks by the measured
figure: a measurement, labeled as one, in the one place a preference
used to speak. With no reference declared, quality remains exactly what
it was in Phase 2: nothing — no pressure, no score, and the explanation
says "quality unmeasured — no reference."
"""
import math
from dataclasses import dataclass

from ..models.registry import (ReliabilityRegistry, source_digest,
                               transform_version, artifact_id)
from ..optimization import quality
from .estimates import estimate

REASON = "TARGET_PRESSURE_MINIMAX"
NO_TARGET_REASON = "STATIC_PRECISION_PREFERENCE_NO_TARGETS_DECLARED"
PRESSURE_EPSILON = 1e-9
# A downgraded candidate's effective worst pressure: its honest pressure
# plus one whole budget. It wins only when every alternative is worse than
# a full budget over its own binding constraint — a last resort.
RELIABILITY_PENALTY = 1.0

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
    downgraded: bool = False
    drift: dict = None  # measured quality drift, when a reference is declared


@dataclass(frozen=True)
class Selection:
    chosen: ScoredCandidate
    scored: tuple
    reason: str
    ranked: tuple = ()


def _pressure(estimated, budget):
    if budget > 0:
        return estimated / budget
    return math.inf if estimated > 0 else 0.0


def _score(spec, profile, candidate, reliability):
    est = estimate(candidate, profile, spec)
    artifact = artifact_id(spec.model_id, source_digest(spec.model_id),
                           candidate.precision,
                           transform_version(candidate.precision),
                           {"backend": candidate.backend})
    pressures = tuple(
        (dim, _pressure(getattr(est, _ESTIMATES[dim]), getattr(spec, _BUDGETS[dim])))
        for dim in _DIMENSIONS if getattr(spec, _BUDGETS[dim]) is not None
    )
    drift = None
    if spec.quality_reference is not None:
        drift = quality.measure_drift(spec.model_id, candidate.precision,
                                      spec.quality_reference)
        if spec.quality_max_drift is not None:
            pressures += (("quality",
                           _pressure(drift["mean_score_error"],
                                     spec.quality_max_drift)),)
    worst = max((p for _, p in pressures), default=None)
    binding = next((dim for dim, p in pressures if p == worst), None)
    downgraded = reliability.is_downgraded(candidate.backend, spec.model_id,
                                            candidate.precision)
    return ScoredCandidate(candidate, est, artifact, pressures, worst, binding,
                           downgraded, drift)


def _optimize_key(spec, scored):
    """The tie-break's first step: the dimension the workload asked to
    optimize. `quality` keys on measured drift when a reference was
    declared — a measurement, not a preference. Without a measurement it
    falls back to the standing precision *preference*, labeled as one."""
    if spec.optimize_for == "quality":
        if scored.drift is not None:
            return scored.drift["mean_score_error"]
        return scored.candidate.preference_rank
    return getattr(scored.estimate, _ESTIMATES[spec.optimize_for])


def _effective_worst(scored):
    """Worst pressure as selection sees it: the honest figure, plus the
    reliability penalty when the entry stands downgraded."""
    if scored.worst_pressure is None:
        return math.inf
    return scored.worst_pressure + (RELIABILITY_PENALTY if scored.downgraded
                                    else 0.0)


def _choose(spec, pool):
    """The winner among a pool of scored candidates — the Phase 2 decision
    rule, unchanged when nothing in the pool is downgraded. Whether any
    budget was declared is read off the scored pressures themselves, so a
    quality-only declaration (Phase 4) takes the minimax path too."""
    if not pool[0].pressures:
        return min(pool, key=lambda s: (1 if s.downgraded else 0,
                                        s.candidate.preference_rank,
                                        s.candidate.backend, s.artifact))
    lowest = min(_effective_worst(s) for s in pool)
    tied = [s for s in pool if _effective_worst(s) - lowest <= PRESSURE_EPSILON]
    return min(tied, key=lambda s: (_optimize_key(spec, s), s.estimate.estimated_cost,
                                    s.candidate.backend, s.artifact))


def _rank(spec, scored):
    """Every survivor in decision order: choose, remove, choose again.
    The fallback order is the selection rule applied repeatedly, not a
    second, simpler sort that could disagree with the choice itself."""
    remaining = list(scored)
    ranked = []
    while remaining:
        winner = _choose(spec, remaining)
        ranked.append(winner)
        remaining.remove(winner)
    return tuple(ranked)


def select(spec, profile, candidates, reliability=None):
    """The winning candidate, with every survivor's scores and the ranked
    fallback order attached. `reliability` defaults to an empty registry —
    every claim trusted — so a caller with no memory to consult gets the
    Phase 2 behavior exactly."""
    registry = reliability if reliability is not None else ReliabilityRegistry()
    scored = tuple(_score(spec, profile, c, registry) for c in candidates)
    ranked = _rank(spec, scored)
    return Selection(ranked[0], scored,
                     REASON if scored[0].pressures else NO_TARGET_REASON, ranked)
