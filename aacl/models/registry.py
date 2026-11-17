"""Model registry: the models the runtime can serve, and their artifact identity.

Phase 0 held exactly one model — the v0.1 proof's fixed, hand-authored linear
classifier — identified by the SHA-256 of its canonical content.

Phase 1 generalizes artifact identity (companion §3): an artifact is named by
everything that determines its bytes —

    artifact_id = hash(model_id, source_digest, precision,
                       transform_version, backend_constraints)

— encoded canonically (JSON, sorted keys, compact separators, constraints
normalized to sorted key/value pairs) so the same inputs always produce the
same id, across runs and across dict orderings. The old ARTIFACT_ID was the
hash of the model alone; that value is now the model's *source digest*, kept
under both names so Phase 0 references still resolve.

Phase 3 adds the registry's memory of behavior: a ReliabilityRegistry
records capability lies against the (backend, model, precision) that
committed them. Every claim starts trusted; a lie downgrades the entry, and
planning deprioritizes downgraded entries — a last resort, never a ban.

Phase 4 registers a second model — iris-logreg-v1, genuinely trained
(models/iris.py) — and with it the per-model form of everything above:
each model has its own source digest, computed from its own content the
same way the demo's always was; the transform version is per precision
(identity for the floating-point artifacts, the quantization service's
version for int8); and the named quality references live here, each
belonging to exactly one model, so a workload can only name a reference
that can actually be measured for the model it asked for.
"""
import hashlib
import json

from . import iris as _iris
from .iris_data import EVAL_REFERENCE as _IRIS_EVAL_REFERENCE

MODEL = {"id": "linear-demo-v1", "weights": [0.75, -0.5, 0.25, 1.0], "bias": -0.125}

# Every model the runtime can serve, by id. The demo is the proof's fixed
# model; iris-logreg-v1 is the trained one.
MODELS = {MODEL["id"]: MODEL, _iris.MODEL["id"]: _iris.MODEL}


def get_model(model_id):
    return MODELS[model_id]


def _source_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


# The digest of the model's source content, exactly as computed in Phase 0.
SOURCE_DIGEST = _source_digest(MODEL)

# Phase 0 name for the source digest, retained for compatibility.
ARTIFACT_ID = SOURCE_DIGEST


def source_digest(model_id):
    """The source digest of one model: the hash of its canonical content,
    computed for every model the way the demo's was in Phase 0."""
    return _source_digest(MODELS[model_id])


# The transformation applied to the source to produce the artifact. Phase 1
# applies none — the artifact is the source, evaluated at a precision — so the
# version names that honestly. Phase 4's quantization service mints the int8
# version; the floating-point artifacts keep the identity version.
TRANSFORM_VERSION = "identity-v1"
INT8_TRANSFORM_VERSION = "int8-v1"
TRANSFORM_VERSIONS = {"fp64": TRANSFORM_VERSION, "fp32": TRANSFORM_VERSION,
                      "int8": INT8_TRANSFORM_VERSION}


def transform_version(precision):
    return TRANSFORM_VERSIONS[precision]


# Named quality references (eval sets), and the one model each belongs to.
# A reference names a measurement that exists: today that is the trained
# model's eval split, "iris-eval-v1" (models/iris_data.py). The demo model
# has no eval set, so it has no reference a workload may name.
QUALITY_REFERENCES = {_IRIS_EVAL_REFERENCE: _iris.MODEL_ID}

# The width of one model element at each precision. It lives here, with the
# artifact definition, because both the estimator (bytes moved) and the
# cache (bytes retained) are accounting for the same artifact.
BYTES_PER_ELEMENT = {"fp64": 8, "fp32": 4, "int8": 1}


def parameter_count(model_id):
    """The number of scalar parameters in a model: weights plus biases,
    however they are shaped."""
    model = MODELS[model_id]
    weights = model["weights"]
    if weights and isinstance(weights[0], list):
        count = sum(len(row) for row in weights) + len(model["bias"])
    else:
        count = len(weights) + 1
    return count


def artifact_size_bytes(model_id, precision):
    """Bytes of one artifact's parameters at this precision. This is the
    size the artifact cache accounts for — the artifact itself, not the
    workspace around it."""
    return parameter_count(model_id) * BYTES_PER_ELEMENT[precision]


class ReliabilityRegistry:
    """Observed reliability of claimed capabilities.

    Keyed by (backend, model_id, precision) — the capability that was
    claimed, for the model family it was claimed about. The record starts
    empty: every claim is trusted until it fails. A capability lie marks
    the entry downgraded; the planner deprioritizes downgraded entries but
    never excludes them. A downgrade does not decay within a process —
    earning trust back is a question for the adaptive phases, and this
    registry does not pretend to answer it yet.
    """

    def __init__(self):
        self._entries = {}

    def record_lie(self, backend, model_id, precision):
        entry = self._entries.setdefault(
            (backend, model_id, precision), {"lies": 0, "downgraded": False})
        entry["lies"] += 1
        entry["downgraded"] = True

    def is_downgraded(self, backend, model_id, precision):
        entry = self._entries.get((backend, model_id, precision))
        return bool(entry and entry["downgraded"])

    def lies(self, backend, model_id, precision):
        entry = self._entries.get((backend, model_id, precision))
        return entry["lies"] if entry else 0

    def downgraded_entries(self):
        return tuple(sorted(key for key, entry in self._entries.items()
                            if entry["downgraded"]))


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _normalize_constraints(backend_constraints):
    """Constraints as a sorted list of [key, value] pairs, whatever order or
    mapping/sequence shape the caller supplied."""
    if backend_constraints is None:
        return []
    if isinstance(backend_constraints, dict):
        pairs = [[str(k), str(v)] for k, v in backend_constraints.items()]
    else:
        pairs = [[str(k), str(v)] for k, v in backend_constraints]
    return sorted(pairs)


def artifact_id(model_id, source_digest, precision, transform_version,
                backend_constraints):
    """The deterministic identity of one executable artifact."""
    payload = {
        "model_id": model_id,
        "source_digest": source_digest,
        "precision": precision,
        "transform_version": transform_version,
        "backend_constraints": _normalize_constraints(backend_constraints),
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()
