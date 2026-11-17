"""Receipt stubs. Signed delegation receipts are the endgame (Phase 7, M10);
Phase 1 introduces only the *shape*: the fields a receipt will one day sign —
which plan ran, on which artifact, where — with the signature explicitly
absent. status is "unsigned" and signature is null. Nothing here is
cryptography, and nothing pretends to be: a stub is a promise about the
record's shape, not about its authenticity.
"""
import hashlib
import json


def build_receipt_stub(selected, spec, request_id):
    identity = json.dumps(
        {"plan_id": selected.plan_id, "artifact_id": selected.artifact_id,
         "request_id": request_id},
        sort_keys=True,
    )
    return {
        "receipt_id": hashlib.sha256(identity.encode()).hexdigest()[:16],
        "status": "unsigned",
        "signature": None,
        "plan_id": selected.plan_id,
        "artifact_id": selected.artifact_id,
        "model_id": spec.model_id,
        "backend": selected.candidate.backend,
        "precision": selected.candidate.precision,
    }
