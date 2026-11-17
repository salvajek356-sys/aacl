"""Static capability estimates: what a candidate is expected to cost, stated
as estimates — never as measurements (companion §1; roadmap M3).

The model is deliberately simple, and every constant in it is named here so
the arithmetic can be argued with:

- An inference moves bytes: the model's parameters, the input vector, and
  one output value, each at the candidate precision's element width. Wider
  elements move more bytes; that is the entire reason fp32 estimates lower
  than fp64.
- Latency = a fixed dispatch overhead plus a per-byte rate over the bytes
  moved. A single tiny vector operation does not parallelize, so the
  discovered core count does not enter this estimate; cores are registry
  facts for the phases that schedule concurrent work (Phases 6–7).
- Memory = the artifact's parameters, the input/output workspace, and one
  page of runtime overhead per loaded artifact.
- Cost = estimated latency at a fixed static rate, in the abstract units
  `cost_budget` is declared in.

Nothing here times anything. Measured timings live in telemetry; these
figures exist so the scorer has something honest to score before any
measurement history exists (correcting them from observations is Phase 6).
"""
from dataclasses import dataclass

from ..models.registry import MODEL

BYTES_PER_ELEMENT = {"fp64": 8, "fp32": 4, "int8": 1}

DISPATCH_OVERHEAD_MS = 0.005
PER_BYTE_MS = 0.0002
RUNTIME_OVERHEAD_BYTES = 4096
COST_UNITS_PER_MS = 0.001
BYTES_PER_MB = 1_000_000


@dataclass(frozen=True)
class CandidateEstimate:
    estimated_latency_ms: float
    estimated_memory_mb: float
    estimated_cost: float


def _clean(value):
    """Round a static estimate to 12 significant digits. The model's
    constants are exact decimals; binary float arithmetic is not, and an
    explanation that prints 0.013000000000000001 ms is noise, not precision.
    Twelve digits is far inside the honesty envelope of a static estimate,
    and the rounding is deterministic."""
    return float(f"{value:.12g}")


def estimate(candidate, profile, spec):
    """The static estimate for one candidate under one backend profile.

    `profile` is part of the signature because an estimate is a claim about
    a candidate *on a backend*: a precision the profile does not list is not
    estimated but refused, rather than priced as if it could run.
    """
    if candidate.precision not in profile.precisions:
        raise ValueError(f"{profile.name} does not offer {candidate.precision}")
    width = BYTES_PER_ELEMENT[candidate.precision]
    parameters = len(MODEL["weights"]) + 1  # weights + bias
    inputs = len(spec.input)
    bytes_moved = (parameters + inputs + 1) * width
    latency_ms = DISPATCH_OVERHEAD_MS + bytes_moved * PER_BYTE_MS
    memory_bytes = parameters * width + (inputs + 1) * width + RUNTIME_OVERHEAD_BYTES
    return CandidateEstimate(
        estimated_latency_ms=_clean(latency_ms),
        estimated_memory_mb=_clean(memory_bytes / BYTES_PER_MB),
        estimated_cost=_clean(latency_ms * COST_UNITS_PER_MS),
    )
