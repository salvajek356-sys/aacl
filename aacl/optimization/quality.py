"""Measured quality: drift against a named reference (companion §4; Phase 4).

Quality exists in this runtime only as a measurement against a named
reference — an eval set, fixed in the repo, evaluated against the
model's floating-point (fp64) artifact. `measure_drift` runs both
artifacts over every eval row and reports what actually differed:

- `label_disagreements` / `label_disagreement_rate` — how often the
  candidate artifact's label differs from the reference's;
- `max_score_error` / `mean_score_error` — how far the candidate's
  class scores sit from the reference's, over all rows and classes.

The workload's `quality_max_drift` tolerance is defined against the
**mean score error**: it is the drift figure that moves for every lossy
artifact (fp32's label disagreements on this eval set are zero, and so
are int8's — a tolerance on the disagreement rate alone could not tell
them apart, while their score errors differ by five orders of
magnitude). Label disagreements are still measured and recorded
alongside; they are evidence, just not the tolerance's unit.

Measurements are computed, never hardcoded, and deterministic: the eval
set, the artifacts, and the arithmetic are all fixed, so the same
(model, precision, reference) always yields the same figures. Results
are memoized per process; callers receive a copy.
"""
from ..backends.cpu import f32
from ..models import iris
from ..models.iris_data import EVAL_ROWS
from . import quantization

# The eval rows behind each named reference. A reference is registered
# here only when its eval set exists in the repo; the registry
# (models/registry.py) names which model each reference belongs to.
_EVAL_SETS = {"iris-eval-v1": EVAL_ROWS}

_cache = {}


def eval_size(reference):
    return len(_EVAL_SETS[reference])


def _candidate_logits(model, precision, values):
    if precision == "int8":
        return quantization.execute_int8(
            quantization.build_int8_artifact(model["id"]), values)
    cast = f32 if precision == "fp32" else float
    return iris.logits(model["weights"], model["bias"], values, cast)


def measure_drift(model_id, precision, reference):
    """The measured drift of one artifact against the named reference.

    The reference artifact is the model's fp64 execution; a candidate at
    fp64 therefore measures exactly zero, by computation, not by fiat.
    """
    key = (model_id, precision, reference)
    if key in _cache:
        return dict(_cache[key])
    from ..models.registry import get_model
    model = get_model(model_id)
    rows = _EVAL_SETS[reference]
    disagreements = 0
    errors = []
    for values, _truth in rows:
        reference_scores = iris.logits(model["weights"], model["bias"], values)
        candidate_scores = _candidate_logits(model, precision, values)
        reference_label = max(range(len(reference_scores)),
                              key=lambda c: reference_scores[c])
        candidate_label = max(range(len(candidate_scores)),
                              key=lambda c: candidate_scores[c])
        disagreements += reference_label != candidate_label
        errors.extend(abs(a - b) for a, b in zip(reference_scores, candidate_scores))
    drift = {
        "reference": reference,
        "eval_samples": len(rows),
        "label_disagreements": disagreements,
        "label_disagreement_rate": disagreements / len(rows),
        "max_score_error": max(errors),
        "mean_score_error": sum(errors) / len(errors),
    }
    _cache[key] = drift
    return dict(drift)
