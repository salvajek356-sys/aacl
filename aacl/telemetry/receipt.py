"""Receipt stubs. Signed delegation receipts are the endgame (Phase 7, M10);
Phase 1 introduces only the *shape*: the fields a receipt will one day sign —
which plan ran, on which artifact, where — with the signature explicitly
absent. status is "unsigned" and signature is null. Nothing here is
cryptography, and nothing pretends to be: a stub is a promise about the
record's shape, not about its authenticity.

Phase 3: when execution fell back, the receipt names what actually ran —
the executed candidate and artifact — under the plan's id. The plan is the
decision; the receipt is the run. The attempts in telemetry connect them.
"""
import hashlib
import json


def build_receipt_stub(selected, spec, request_id, executed=None):
    if executed is not None:
        candidate, artifact = executed
        backend, precision = candidate.backend, candidate.precision
    else:
        artifact = selected.artifact_id
        backend, precision = selected.candidate.backend, selected.candidate.precision
    identity = json.dumps(
        {"plan_id": selected.plan_id, "artifact_id": artifact,
         "request_id": request_id},
        sort_keys=True,
    )
    return {
        "receipt_id": hashlib.sha256(identity.encode()).hexdigest()[:16],
        "status": "unsigned",
        "signature": None,
        "plan_id": selected.plan_id,
        "artifact_id": artifact,
        "model_id": spec.model_id,
        "backend": backend,
        "precision": precision,
    }
