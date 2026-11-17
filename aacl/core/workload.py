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
here, and `optimize_for` orders its tie-breaks.

Phase 4 makes quality real, and the spec grows the one field that
requires: `quality_max_drift`, the maximum acceptable *mean score error*
against the named reference (see optimization/quality.py for why the
tolerance is on score error and not the label-disagreement rate, which
is measured and recorded alongside it). A `quality_reference` must now
name a registered eval set for the requested model — an unknown name is
a typed refusal, not a note carried forever — and a drift tolerance
without a reference to measure against is refused for the same reason.
A second model is installed (iris-logreg-v1, trained), so `model_id`
is checked against the registry rather than against one fixed id.
"""
import math
from dataclasses import dataclass

from ..models.registry import MODELS, QUALITY_REFERENCES


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
           "optimize_for", "quality_reference", "quality_max_drift"}


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
    quality_max_drift: float = None

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise Rejection("INVALID_REQUEST", "Expected a JSON object")
        if set(raw) - _FIELDS:
            raise Rejection("INVALID_REQUEST", "Unknown fields; unsupported constraints are never ignored")
        model_id = raw.get("model_id", "linear-demo-v1")
        if model_id not in MODELS:
            raise Rejection("UNKNOWN_MODEL",
                            f"Unknown model; installed: {', '.join(sorted(MODELS))}")
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
            if QUALITY_REFERENCES.get(quality_reference) != model_id:
                raise Rejection(
                    "UNKNOWN_QUALITY_REFERENCE",
                    f"No quality reference '{quality_reference}' is registered "
                    f"for model {model_id}; a reference names an eval set that "
                    f"exists, or the request is refused")
        quality_max_drift = _number(raw, "quality_max_drift", 0, exclusive=False)
        if quality_max_drift is not None and quality_reference is None:
            raise Rejection(
                "INVALID_REQUEST",
                "quality_max_drift requires a quality_reference to measure against")
        return cls(model_id, tuple(values), tuple(precisions), local,
                   latency, memory, cost, optimize_for, quality_reference,
                   quality_max_drift)
