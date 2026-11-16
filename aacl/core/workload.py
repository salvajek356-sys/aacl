"""WorkloadSpec: the runtime's normalized description of a job.

Ported unchanged from the v0.1 proof: unknown fields are rejected, never
silently ignored, so unsupported constraints are never promised.
"""
import math
from dataclasses import dataclass

from ..models.registry import MODEL


class Rejection(ValueError):
    """A typed refusal: machine-readable code plus a human message."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WorkloadSpec:
    model_id: str
    input: tuple
    allowed_precisions: tuple
    local_only: bool

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise Rejection("INVALID_REQUEST", "Expected a JSON object")
        if set(raw) - {"model_id", "input", "allowed_precisions", "local_only"}:
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
        return cls(MODEL["id"], tuple(values), tuple(precisions), local)
