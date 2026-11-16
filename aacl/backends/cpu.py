"""The CPU reference backend. Not a temporary hack: the baseline every later
backend is compared against (roadmap §5). Execution math — including the
explicit fp32 rounding at every step — is the v0.1 proof's, unchanged."""
import struct

from ..core.capabilities import BackendProfile
from ..core.workload import Rejection
from ..models.registry import ARTIFACT_ID, MODEL


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


class CPUBackend:
    def capabilities(self):
        return BackendProfile()

    def execute(self, selected, values):
        if selected.artifact_id != ARTIFACT_ID or selected.candidate.backend != "cpu-python":
            raise Rejection("INVALID_PLAN", "Artifact or backend mismatch")
        precision = selected.candidate.precision
        if precision not in self.capabilities().precisions:
            raise Rejection("INVALID_PLAN", "Unsupported precision")
        cast = f32 if precision == "fp32" else float
        score = cast(MODEL["bias"])
        for weight, value in zip(MODEL["weights"], values):
            score = cast(score + cast(cast(weight) * cast(value)))
        return {"score": score, "label": int(score >= 0)}
