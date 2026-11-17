"""The CPU reference backend. Not a temporary hack: the baseline every later
backend is compared against (roadmap §5). Execution math — including the
explicit fp32 rounding at every step — is the v0.1 proof's, unchanged.

Phase 1: execution goes through the async handle contract (companion §5).
The CPU backend is synchronous, so submit() runs the work at once and returns
an already-completed handle. execute() remains as a thin synchronous
convenience over that contract, for callers (like prove.py) that measure the
direct path.
"""
import struct

from ..core.capabilities import BackendProfile
from ..core.workload import Rejection
from ..models.registry import MODEL, SOURCE_DIGEST, TRANSFORM_VERSION, artifact_id
from .base import CompletedHandle


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


class CPUBackend:
    def capabilities(self):
        return BackendProfile()

    def submit(self, selected, values):
        try:
            return CompletedHandle(output=self._run(selected, values))
        except Exception as exc:
            return CompletedHandle(error=exc)

    def execute(self, selected, values):
        return self.submit(selected, values).result()

    def _run(self, selected, values):
        expected = artifact_id(MODEL["id"], SOURCE_DIGEST,
                               selected.candidate.precision, TRANSFORM_VERSION,
                               {"backend": self.capabilities().name})
        if selected.artifact_id != expected or selected.candidate.backend != "cpu-python":
            raise Rejection("INVALID_PLAN", "Artifact or backend mismatch")
        precision = selected.candidate.precision
        if precision not in self.capabilities().precisions:
            raise Rejection("INVALID_PLAN", "Unsupported precision")
        cast = f32 if precision == "fp32" else float
        score = cast(MODEL["bias"])
        for weight, value in zip(MODEL["weights"], values):
            score = cast(score + cast(cast(weight) * cast(value)))
        return {"score": score, "label": int(score >= 0)}
