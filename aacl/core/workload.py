"""WorkloadSpec: the runtime's normalized description of a job.

Phase 0 (the v0.1 proof): unknown fields are rejected, never silently
ignored, so unsupported constraints are never promised.

Phase 1 (contracts v2) grows the spec: a workload may now declare a latency
target, a memory limit, a cost budget, an `optimize_for` preference, and a
`quality_reference` naming the reference its quality would be measured
against. Every value is validated — a negative budget or an `optimize_for`
outside the supported set is a typed refusal, not a quiet default.

Phase 2 puts the declared budgets to work: the planner scores candidates by
target pressure against the latency, memory, and cost figures declared
here, and `optimize_for` orders its tie-breaks. The one field that still
does not steer anything is `quality_reference`: quality is unmeasured until
Phase 4, so a declared reference is carried and named, and contributes no
score — the plan's explanation says so rather than letting a declared
reference look honored when it was only noted.
"""
import math
from dataclasses import dataclass

from ..models.registry import MODEL


class Rejection(ValueError):
    """A typed refusal: machine-readable code plus a human message."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# The preferences a workload may ask the planner to optimize for. Phase 1
# validated and recorded the choice; Phase 2's scorer acts on it as the
# first tie-break after worst target pressure.
OPTIMIZE_FOR = ("latency", "quality", "cost", "memory")

_FIELDS = {"model_id", "input", "allowed_precisions", "local_only",
           "latency_target_ms", "memory_limit_mb", "cost_budget",
           "optimize_for", "quality_reference"}


def _number(raw, field, minimum, exclusive):
    """A validated optional numeric target, or None when undeclared."""
    value = raw.get(field)
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Rejection("INVALID_REQUEST", f"{field} must be a finite number")
    if exclusive and not value > minimum:
        raise Rejection("INVALID_REQUEST", f"{field} must be greater than {minimum}")
    if not exclusive and not value >= minimum:
        raise Rejection("INVALID_REQUEST", f"{field} must be at least {minimum}")
    return float(value)


@dataclass(frozen=True)
class WorkloadSpec:
    model_id: str
    input: tuple
    allowed_precisions: tuple
    local_only: bool
    latency_target_ms: float = None
    memory_limit_mb: float = None
    cost_budget: float = None
    optimize_for: str = "latency"
    quality_reference: str = None

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise Rejection("INVALID_REQUEST", "Expected a JSON object")
        if set(raw) - _FIELDS:
            raise Rejection("INVALID_REQUEST", "Unknown fields; unsupported constraints are never ignored")
        if raw.get("model_id", MODEL["id"]) != MODEL["id"]:
            raise Rejection("UNKNOWN_MODEL", "Only linear-demo-v1 is installed")
        values = raw.get("input")
        if not isinstance(values, list) or len(values) != 4 or any(
            type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1000 for x in values
        ):
            raise Rejection("INVALID_INPUT", "Expected four finite numbers in [-1000, 1000]")
        precisions = raw.get("allowed_precisions", ["fp32", "fp64"])
        if not isinstance(precisions, list) or not precisions or any(
            p not in ("fp32", "fp64", "int8") for p in precisions
        ):
            raise Rejection("INVALID_REQUEST", "Invalid allowed_precisions")
        local = raw.get("local_only", True)
        if type(local) is not bool:
            raise Rejection("INVALID_REQUEST", "local_only must be boolean")
        latency = _number(raw, "latency_target_ms", 0, exclusive=True)
        memory = _number(raw, "memory_limit_mb", 0, exclusive=True)
        cost = _number(raw, "cost_budget", 0, exclusive=False)
        optimize_for = raw.get("optimize_for", "latency")
        if optimize_for not in OPTIMIZE_FOR:
            raise Rejection("INVALID_REQUEST",
                            f"optimize_for must be one of {', '.join(OPTIMIZE_FOR)}")
        quality_reference = raw.get("quality_reference")
        if quality_reference is not None:
            if not isinstance(quality_reference, str) or not quality_reference.strip() \
                    or len(quality_reference) > 128:
                raise Rejection("INVALID_REQUEST",
                                "quality_reference must be a non-empty string naming a reference")
            quality_reference = quality_reference.strip()
        return cls(MODEL["id"], tuple(values), tuple(precisions), local,
                   latency, memory, cost, optimize_for, quality_reference)
