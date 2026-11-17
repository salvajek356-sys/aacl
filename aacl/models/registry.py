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
"""
import hashlib
import json

MODEL = {"id": "linear-demo-v1", "weights": [0.75, -0.5, 0.25, 1.0], "bias": -0.125}

# The digest of the model's source content, exactly as computed in Phase 0.
SOURCE_DIGEST = hashlib.sha256(json.dumps(MODEL, sort_keys=True).encode()).hexdigest()

# Phase 0 name for the source digest, retained for compatibility.
ARTIFACT_ID = SOURCE_DIGEST

# The transformation applied to the source to produce the artifact. Phase 1
# applies none — the artifact is the source, evaluated at a precision — so the
# version names that honestly. Quantization (Phase 4) mints new versions here.
TRANSFORM_VERSION = "identity-v1"


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
