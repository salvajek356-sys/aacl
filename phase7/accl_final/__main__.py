"""Run: python3 -m accl_final {digest,run,verify}.

Evidence files are written with exclusive creation: an
existing file is never overwritten.
"""
import argparse
import json
import sys
from pathlib import Path

from .canonical import InvalidArtifact, digest, load_json
from .contract import validate_contract
from .execute import execute
from .verify import verify

_AXES = ("contract_binding", "receipt_structure", "computational_verdict",
         "artifact_integrity", "execution_provenance", "overall_verdict")


def write_new(path, obj):
    path = Path(path)
    body = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True,
                      allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(body)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="ACCL Phase 7 — contracts, receipts, independent verification")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("digest", help="print canonical SHA256 of a valid contract")
    p.add_argument("--contract", required=True)
    p = sub.add_parser("run", help="execute the contract and create its receipt")
    p.add_argument("--contract", required=True)
    p.add_argument("--receipt", required=True)
    p = sub.add_parser("verify", help="independently verify a receipt")
    p.add_argument("--contract", required=True)
    p.add_argument("--artifact", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--trusted-contract-sha256", required=True)
    p.add_argument("--trusted-artifact-sha256", required=True)
    p.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        validate_contract(contract)
        if args.command == "digest":
            print(digest(contract))
            return 0
        if args.command == "run":
            path = write_new(args.receipt, execute(contract))
            print(f"RECEIPT: {path}")
            print("SELF-REPORTED EXECUTION; NOT HARDWARE ATTESTATION")
            return 0
        report = verify(contract, load_json(args.receipt), args.artifact,
                        args.trusted_contract_sha256,
                        args.trusted_artifact_sha256)
        path = write_new(args.report, report)
        for key in _AXES:
            print(f"{key.upper()}: {report[key]}")
        print(f"REPORT: {path}")
        return 0 if report["overall_verdict"] == "PASS" else 1
    except (InvalidArtifact, ValueError, OSError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
