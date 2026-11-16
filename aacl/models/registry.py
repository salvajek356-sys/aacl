"""Model registry: the models the runtime can serve, and their artifact identity.

Phase 0 holds exactly one model — the v0.1 proof's fixed, hand-authored linear
classifier — identified by the SHA-256 of its canonical content, as in the proof.
"""
import hashlib
import json

MODEL = {"id": "linear-demo-v1", "weights": [0.75, -0.5, 0.25, 1.0], "bias": -0.125}
ARTIFACT_ID = hashlib.sha256(json.dumps(MODEL, sort_keys=True).encode()).hexdigest()
