"""Quantization as a transformation service (roadmap §9; Phase 4).

The service owns the whole transformation: it takes a model's
floating-point source, runs the calibration data itself, derives the
quantization scales, and produces the int8 artifact. The planner never
grows quantization logic of its own — it asks the service which
transforms exist for a model, and the backend asks it for the artifact
to execute.

Calibration ownership is the point. An int8 artifact is meaningless
without the data its scales came from, so the scales are not inputs a
caller supplies: the service runs the model's calibration split (for
iris-logreg-v1, the 30 calibration rows of the embedded Iris dataset)
and derives —

- one symmetric per-tensor weight scale: max |weight| / 127;
- one symmetric input scale from the calibration inputs: max |x| / 127.

Execution is genuinely integer: inputs and weights are int8 values, the
dot product and the (quantized) bias accumulate in exact Python ints,
and a single float multiplication by weight_scale * input_scale at the
end recovers the logit. Nothing is dequantized element-by-element back
into a float model; the artifact that runs is the integer one.

Only models with calibration data have transforms. The demo model has
none — no calibration set, no eval reference — so the service registers
no transform for it, and int8 stays unoffered there rather than being
invented for it.
"""
from ..models import iris
from ..models.iris_data import CALIBRATION_ROWS

INT8_PRECISION = "int8"
INT8_TRANSFORM_VERSION = "int8-v1"

# Models the service can transform, and the calibration rows it runs for
# each. Registration is the service's own statement: a model appears here
# only when calibration data for it exists in the repo.
_CALIBRATION = {iris.MODEL_ID: CALIBRATION_ROWS}

_cache = {}


def has_transform(model_id):
    """Whether an int8 transform exists for this model."""
    return model_id in _CALIBRATION


def _quantize_value(value, scale):
    return max(-127, min(127, round(value / scale)))


def build_int8_artifact(model_id):
    """The int8 artifact for a model, built by calibrating on the
    model's calibration split. Deterministic — same model, same
    calibration data, same artifact — and memoized per process."""
    if model_id in _cache:
        return _cache[model_id]
    if model_id not in _CALIBRATION:
        raise ValueError(f"no int8 transform registered for {model_id}")
    from ..models.registry import get_model
    model = get_model(model_id)
    weights, bias = model["weights"], model["bias"]
    calibration = _CALIBRATION[model_id]
    weight_scale = max(abs(w) for row in weights for w in row) / 127
    input_scale = max(abs(v) for x, _ in calibration for v in x) / 127
    combined = weight_scale * input_scale
    artifact = {
        "model_id": model_id,
        "precision": INT8_PRECISION,
        "transform_version": INT8_TRANSFORM_VERSION,
        "weight_ints": [[_quantize_value(w, weight_scale) for w in row]
                        for row in weights],
        "bias_ints": [max(-(2 ** 31), min(2 ** 31 - 1, round(b / combined)))
                      for b in bias],
        "weight_scale": weight_scale,
        "input_scale": input_scale,
    }
    _cache[model_id] = artifact
    return artifact


def execute_int8(artifact, values):
    """Run an int8 artifact: quantize the input, accumulate the dot
    products and bias in integers, dequantize once at the end. Returns
    the class scores (logits)."""
    input_scale = artifact["input_scale"]
    combined = artifact["weight_scale"] * input_scale
    quantized_input = [_quantize_value(v, input_scale) for v in values]
    scores = []
    for c, row in enumerate(artifact["weight_ints"]):
        accumulator = artifact["bias_ints"][c]
        for j, qx in enumerate(quantized_input):
            accumulator += row[j] * qx
        scores.append(accumulator * combined)
    return scores
