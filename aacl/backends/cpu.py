"""The CPU reference backend. Not a temporary hack: the baseline every later
backend is compared against (roadmap §5). Execution math — including the
explicit fp32 rounding at every step — is the v0.1 proof's, unchanged.

Phase 1: execution goes through the async handle contract (companion §5).
The CPU backend is synchronous, so submit() runs the work at once and returns
an already-completed handle. execute() remains as a thin synchronous
convenience over that contract, for callers (like prove.py) that measure the
direct path.

Phase 4: there are two models and a third precision. The backend dispatches
on the plan's model: the demo keeps its original math; the trained model
runs its softmax-regression scores at fp64 or with fp32 rounding; and int8
runs the transformation service's integer artifact — quantized inputs,
integer accumulation, one dequantizing multiply at the end. A plan naming
int8 for a model with no registered transform is refused as invalid: the
artifact it names cannot exist.
"""
import struct

from ..core.capabilities import BackendProfile
from ..core.workload import Rejection
from ..models import iris
from ..models.registry import (artifact_id, get_model, source_digest,
                               transform_version)
from ..optimization import quantization
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
        model = get_model(selected.model_id)
        precision = selected.candidate.precision
        expected = artifact_id(selected.model_id, source_digest(selected.model_id),
                               precision, transform_version(precision),
                               {"backend": self.capabilities().name})
        if selected.artifact_id != expected or selected.candidate.backend != "cpu-python":
            raise Rejection("INVALID_PLAN", "Artifact or backend mismatch")
        if precision not in self.capabilities().precisions:
            raise Rejection("INVALID_PLAN", "Unsupported precision")
        if precision == "int8":
            if not quantization.has_transform(selected.model_id):
                raise Rejection("INVALID_PLAN",
                                "No int8 artifact exists for this model")
            artifact = quantization.build_int8_artifact(selected.model_id)
            scores = quantization.execute_int8(artifact, values)
            return self._classification(model, scores)
        if model.get("kind") == "multinomial-logreg":
            cast = f32 if precision == "fp32" else float
            scores = iris.logits(model["weights"], model["bias"], values, cast)
            return self._classification(model, scores)
        cast = f32 if precision == "fp32" else float
        score = cast(model["bias"])
        for weight, value in zip(model["weights"], values):
            score = cast(score + cast(cast(weight) * cast(value)))
        return {"score": score, "label": int(score >= 0)}

    @staticmethod
    def _classification(model, scores):
        label = max(range(len(scores)), key=lambda c: scores[c])
        return {"scores": scores, "label": label,
                "label_name": model["classes"][label]}
