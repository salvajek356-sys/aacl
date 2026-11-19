# ACCL Phase 7 — Execution Receipts (Final Architecture)

> ACCL is an experimental system for independently evaluating
> whether computational results and supplied execution
> artifacts satisfy explicitly declared contracts, while
> distinguishing verified evidence from unsupported execution
> claims.

An AI agent reports: *task completed successfully.* How would
you know? This package is a small, complete demonstration of
one answer: the work is declared in a **contract** before it
runs, the run produces a **receipt** binding what was
declared to what came out and which program artifact was
supplied, and an **independent verifier** — which trusts
nothing the executor asserted — checks the evidence and
reports separate findings.

Standard library only. No accelerator, no dependencies. The
verification mechanism is easier to inspect than the
computation it verifies.

## Run the demonstration

```bash
bash run_demo.sh
```

That runs the test suite, executes the reference contract,
and verifies the receipt, printing every verdict axis. Or
step by step:

```bash
python3 -m accl_final digest --contract contracts/vector_add_v01.json
python3 -m accl_final run    --contract contracts/vector_add_v01.json \
                             --receipt  evidence/receipt.json
python3 -m accl_final verify --contract contracts/vector_add_v01.json \
    --artifact accl_final/execute.py \
    --receipt  evidence/receipt.json \
    --trusted-contract-sha256 <digest from the digest step> \
    --trusted-artifact-sha256 <sha256 of accl_final/execute.py> \
    --report   evidence/verification.json
```

The two trusted digests must reach the verifier through a
channel independent of the receipt — in this demonstration
you compute them yourself from the files you inspected;
that is the mechanics of a trust anchor, shown honestly at
demonstration scale.

## Run the tests

```bash
python3 -m unittest discover -s tests -t .
```

23 tests: the verdict decision table, strict int32 boundary
conditions, hand-computed independent vectors, and an
adversarial suite (tampered output, altered artifact,
substituted contract, forged hardware claims, missing trust
anchors, malformed and duplicate-member JSON).

## What the verdicts mean

The verifier reports four findings separately:

- **contract_binding** — the contract presented is the
  contract that was authorized (matches the trusted digest).
- **computational_verdict** — the recorded output agrees
  with the verifier's *own* recomputation. The verifier
  implements the arithmetic itself; it shares no code for
  the computation with the executor.
- **artifact_integrity** — the supplied program file is
  byte-identical to the trusted artifact and to the
  receipt's binding.
- **execution_provenance** — **INDETERMINATE**, always, in
  this version. Nothing here authenticates where or on what
  the computation physically ran, and a receipt claiming
  otherwise (one test claims an NPU) changes nothing.

**overall_verdict** is PASS only when every evaluable
dimension passes. Overall PASS means the evidence package
satisfies the implemented integrity and computational
checks. It does **not** mean physical execution has been
authenticated.

## The rules this implementation follows

Locked 2026-11-18 after adversarial review of two earlier
implementations:

1. **Independent computation** — the verifier never reuses
   the executor's arithmetic.
2. **Strict contracts** — signed int32, exact verification;
   a contract whose inputs would overflow is invalid and
   rejected before execution. No silent wraparound.
3. **Independent evidence dimensions** — each verdict
   describes its own result; a correct result from an
   altered artifact reports computation PASS and artifact
   FAIL, not a blurred single failure.
4. **Fail-closed acceptance** — missing required evidence
   prevents overall acceptance.
5. **Explicit uncertainty** — unauthenticated execution
   claims remain indeterminate, in the report, every time.

## Layout

```text
ACCL-Phase7.3/
├── README.md               — this file
├── SPECIFICATION.md        — formats, rules, decision table
├── MANIFEST_SHA256.txt     — integrity manifest for the package
├── run_demo.sh             — tests + demonstration, one command
├── contracts/
│   └── vector_add_v01.json — the reference contract
├── accl_final/
│   ├── canonical.py        — canonical form, digests, strict JSON
│   ├── contract.py         — strict contract validation (no arithmetic)
│   ├── execute.py          — reference executor, receipt builder
│   ├── verify.py           — the independent verifier (own arithmetic)
│   └── __main__.py         — digest / run / verify CLI
├── tests/
│   └── test_final.py
└── evidence/               — demonstration output lands here
```

## Lineage

Phase 7.1 established contracts and a two-axis verifier;
7.2 bound receipts to software artifacts; 7.2.1 separated
the verdicts. This package is the final architecture: it
implements the three locked decisions in a single
self-contained codebase and verifies the historical Phase
7.2 receipt under the same trust anchors. The full record —
including the earlier implementations and their evidence —
is part of the Substrate Research publication record.
