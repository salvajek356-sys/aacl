#!/usr/bin/env bash
# ACCL Phase 7 — one-command demonstration.
# Runs the test suite, executes the reference contract, and
# independently verifies the receipt. Evidence is written to
# a fresh directory and never overwritten.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2

if [ -f MANIFEST_SHA256.txt ]; then
    if ! sha256sum -c MANIFEST_SHA256.txt; then
        echo "STOP: Package integrity failure"; exit 2
    fi
fi

echo "========================================"
echo "ACCL PHASE 7 — EXECUTION RECEIPTS"
echo "========================================"
python3 --version

echo
echo "1. TESTS"
echo "----------------------------------------"
if ! python3 -m unittest discover -s tests -t .; then
    echo "TESTS: FAIL"; exit 1
fi

OUT="$(mktemp -d "$HERE/evidence/phase7.XXXXXXXX")" || exit 2
echo
echo "Evidence directory: $OUT"

echo
echo "2. CONTRACT TRUST ANCHOR"
echo "----------------------------------------"
CONTRACT_SHA="$(python3 -m accl_final digest --contract contracts/vector_add_v01.json)" || exit 1
echo "Trusted canonical contract SHA256: $CONTRACT_SHA"
ARTIFACT_SHA="$(sha256sum accl_final/execute.py | cut -d' ' -f1)"
echo "Trusted artifact SHA256:           $ARTIFACT_SHA"

echo
echo "3. REFERENCE EXECUTION"
echo "----------------------------------------"
python3 -m accl_final run --contract contracts/vector_add_v01.json \
    --receipt "$OUT/receipt.json" || exit 1

echo
echo "4. INDEPENDENT VERIFICATION"
echo "----------------------------------------"
python3 -m accl_final verify --contract contracts/vector_add_v01.json \
    --artifact accl_final/execute.py \
    --receipt "$OUT/receipt.json" \
    --trusted-contract-sha256 "$CONTRACT_SHA" \
    --trusted-artifact-sha256 "$ARTIFACT_SHA" \
    --report "$OUT/verification.json"
RESULT=$?

echo
echo "5. EVIDENCE HASHES"
echo "----------------------------------------"
sha256sum "$OUT/receipt.json" "$OUT/verification.json"

echo
if [ "$RESULT" -eq 0 ]; then
    echo "PHASE 7 DEMONSTRATION: PASS — computation and artifact verified;"
    echo "execution provenance INDETERMINATE, as it must be."
else
    echo "PHASE 7 DEMONSTRATION: FAIL"
fi
exit "$RESULT"
