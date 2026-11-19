"""The independent verifier — final architecture.

Four findings, reported separately, never substituted for one
another (Architecture Decision 3, 2026-11-18):

- contract_binding      — the presented contract matches a
                          trusted digest supplied independently.
- receipt_structure     — the receipt conforms and binds to
                          the contract and its inputs.
- computational_verdict — the recorded output agrees with
                          this verifier's own recomputation.
- artifact_integrity    — the supplied artifact's bytes match
                          the trusted artifact digest and the
                          receipt's binding.
- execution_provenance  — always INDETERMINATE here. Nothing
                          supplied authenticates device,
                          execution, or location.

overall_verdict is FAIL unless every evaluable dimension
passes (fail-closed): missing required evidence prevents
acceptance, and a dimension that cannot be evaluated stays
INDETERMINATE rather than being silently passed or failed on
another dimension's evidence.

Overall PASS means the evidence package satisfies the
implemented integrity and computational checks. It does not
mean physical execution has been authenticated.

The arithmetic below is this module's own implementation,
written for the verifier. It shares with the executor only
schemas, canonicalization, and cryptographic primitives —
never the computation being tested (Architecture Decision 1).
"""
import hmac
from pathlib import Path

from .canonical import (InvalidArtifact, artifact_hash, digest,
                        validate_hex_digest)
from .contract import MAX_I32, MIN_I32, _keys, validate_contract
from .execute import RECEIPT_SCHEMA

REPORT_SCHEMA = "accl.verification-report.v0.3"

_LIMITATIONS = [
    "A matching artifact digest proves supplied byte identity, not that those bytes executed.",
    "Arithmetic agreement is not evidence of physical execution.",
    "Runtime and device claims are untrusted and cannot establish provenance.",
    "Trust anchors must be obtained separately from untrusted evidence.",
    "Overall PASS is evidence acceptance under the implemented checks, not execution authentication.",
]


def _recompute(contract):
    """The verifier's independent implementation of
    vector_add_int32. Kept separate from the executor's on
    purpose; agreement between the two is the cross-check."""
    a = contract["inputs"]["a"]
    b = contract["inputs"]["b"]
    out = []
    for i in range(len(a)):
        out.append(a[i] + b[i])
    return out


def verify(contract, receipt, artifact_path, trusted_contract_sha256,
           trusted_artifact_sha256):
    report = {
        "schema": REPORT_SCHEMA,
        "contract_binding": "INDETERMINATE",
        "receipt_structure": "INDETERMINATE",
        "computational_verdict": "INDETERMINATE",
        "artifact_integrity": "INDETERMINATE",
        "execution_provenance": "INDETERMINATE",
        "overall_verdict": "FAIL",
        "checks": [],
        "limitations": list(_LIMITATIONS),
    }

    def record(category, status, reason):
        report["checks"].append(
            {"category": category, "status": status, "reason": reason})
        report[category] = status

    # Contract first. An untrusted contract gates everything:
    # downstream dimensions stay INDETERMINATE (decision table).
    if not validate_hex_digest(trusted_contract_sha256):
        record("contract_binding", "FAIL",
               "trusted contract digest absent or malformed")
        return report
    try:
        validate_contract(contract)
        contract_hash = digest(contract)
    except (InvalidArtifact, TypeError, ValueError, OverflowError) as exc:
        record("contract_binding", "FAIL", f"invalid contract: {exc}")
        return report
    if not hmac.compare_digest(contract_hash, trusted_contract_sha256):
        record("contract_binding", "FAIL",
               "contract mismatches independent trust anchor")
        return report
    record("contract_binding", "PASS",
           "contract matches independently trusted SHA256")
    report["contract_sha256"] = contract_hash

    # Receipt structure and bindings.
    try:
        _keys(receipt, ("schema", "contract_sha256", "operation", "input_sha256",
                        "output", "output_sha256", "artifact", "claims"),
              "receipt v0.2")
        if receipt["schema"] != RECEIPT_SCHEMA:
            raise InvalidArtifact("unsupported receipt schema")
        if not validate_hex_digest(receipt["contract_sha256"]) \
                or not hmac.compare_digest(receipt["contract_sha256"], contract_hash):
            raise InvalidArtifact("receipt contract digest mismatch")
        if receipt["operation"] != contract["operation"]:
            raise InvalidArtifact("receipt operation mismatch")
        if not validate_hex_digest(receipt["input_sha256"]) \
                or not hmac.compare_digest(receipt["input_sha256"],
                                           digest(contract["inputs"])):
            raise InvalidArtifact("receipt input digest mismatch")
        artifact = receipt["artifact"]
        _keys(artifact, ("name", "sha256"), "artifact")
        if (type(artifact["name"]) is not str or not artifact["name"]
                or "/" in artifact["name"] or "\\" in artifact["name"]
                or artifact["name"] in (".", "..")):
            raise InvalidArtifact("invalid artifact name")
        if not validate_hex_digest(artifact["sha256"]):
            raise InvalidArtifact("invalid receipt artifact SHA256")
        claims = receipt["claims"]
        _keys(claims, ("execution_backend", "execution_location",
                       "hardware_attestation"), "claims")
        if any(type(v) is not str or not v for v in claims.values()):
            raise InvalidArtifact("invalid self-reported execution claims")
        report["claims_as_reported_unverified"] = claims
    except (InvalidArtifact, TypeError, ValueError, OverflowError) as exc:
        record("receipt_structure", "FAIL",
               f"invalid receipt or binding: {exc}")
        return report
    record("receipt_structure", "PASS",
           "receipt schema, contract/input binding, and claims shape valid")

    # Independent computation. No artifact result gates this.
    output = receipt["output"]
    if (type(output) is not list
            or len(output) != contract["requirements"]["output_length"]
            or any(type(v) is not int or not MIN_I32 <= v <= MAX_I32
                   for v in output)):
        record("computational_verdict", "FAIL",
               "output has invalid shape or int32 value")
    elif not validate_hex_digest(receipt["output_sha256"]) \
            or not hmac.compare_digest(receipt["output_sha256"], digest(output)):
        record("computational_verdict", "FAIL",
               "output integrity digest mismatch")
    elif output != _recompute(contract):
        record("computational_verdict", "FAIL",
               "output differs from independently recomputed arithmetic")
    else:
        record("computational_verdict", "PASS",
               "verified exact output against independent arithmetic and output digest")
        report["receipt_output_sha256"] = receipt["output_sha256"]

    # Supplied-byte identity. No arithmetic result gates this.
    if not validate_hex_digest(trusted_artifact_sha256):
        record("artifact_integrity", "INDETERMINATE",
               "trusted artifact digest absent or malformed")
    else:
        try:
            measured = artifact_hash(artifact_path)
            if not hmac.compare_digest(measured, trusted_artifact_sha256):
                record("artifact_integrity", "FAIL",
                       "supplied artifact differs from trusted digest")
            elif not hmac.compare_digest(measured, artifact["sha256"]):
                record("artifact_integrity", "FAIL",
                       "receipt artifact digest mismatch")
            elif Path(artifact_path).name != artifact["name"]:
                record("artifact_integrity", "FAIL",
                       "receipt artifact basename mismatch")
            else:
                record("artifact_integrity", "PASS",
                       "supplied artifact bytes match trust anchor and receipt")
                report["verified_artifact_sha256"] = measured
        except (InvalidArtifact, OSError, ValueError) as exc:
            record("artifact_integrity", "FAIL",
                   f"artifact cannot be verified: {exc}")

    if all(report[key] == "PASS" for key in
           ("contract_binding", "receipt_structure",
            "computational_verdict", "artifact_integrity")):
        report["overall_verdict"] = "PASS"
    return report
