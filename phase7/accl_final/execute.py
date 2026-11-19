"""Reference executor and receipt builder (receipt v0.2).

The executor performs the contract's operation and issues a
self-reported receipt binding the contract digest, the input
digest, the output and its digest, and the supplied software
artifact (by default, this module's own file) by digest.

Everything in a receipt is a claim. The receipt's own line,
printed by the CLI, is: SELF-REPORTED EXECUTION; NOT HARDWARE
ATTESTATION.

The arithmetic here is the executor's implementation. The
verifier implements its own (Architecture Decision 1).
"""
from pathlib import Path

from .canonical import artifact_hash, digest
from .contract import validate_contract

RECEIPT_SCHEMA = "accl.execution-receipt.v0.2"

DEFAULT_CLAIMS = {
    "execution_backend": "python-reference",
    "execution_location": "unattested",
    "hardware_attestation": "absent",
}


def _vector_add(a, b):
    return [x + y for x, y in zip(a, b)]


def make_receipt(contract, artifact_path=None, *, output=None, claims=None):
    validate_contract(contract)
    if artifact_path is None:
        artifact_path = Path(__file__)
    result = _vector_add(contract["inputs"]["a"], contract["inputs"]["b"]) \
        if output is None else output
    return {
        "schema": RECEIPT_SCHEMA,
        "contract_sha256": digest(contract),
        "operation": contract["operation"],
        "input_sha256": digest(contract["inputs"]),
        "output": result,
        "output_sha256": digest(result),
        "artifact": {"name": Path(artifact_path).name,
                     "sha256": artifact_hash(artifact_path)},
        "claims": dict(DEFAULT_CLAIMS) if claims is None else claims,
    }


def execute(contract, artifact_path=None):
    return make_receipt(contract, artifact_path)
