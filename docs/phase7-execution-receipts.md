# Phase 7 — Execution Receipts: the record

Dated record, 2026-11-18. The implementation is in `phase7/`
in this repository. The governing specification is
`docs/execution-receipt-spec-v0.1.md` (frozen 2026-11-18);
the design authority for the final architecture is
`docs/verification-architecture-decisions-2026-11-18.md`.

## Why this phase exists

ACCL was repositioned on 2026-11-18 as the primary project,
with execution receipts as its defining contribution. The
question: *can an independent party establish what an
autonomous system was instructed to execute, what actually
executed, where it executed, and whether the result
satisfied the original contract?* Phase 7 is the first
runnable answer, at demonstration scale: one operation
(`vector_add_int32`), three artifacts (contract, receipt,
verification report), and a verifier that works without
trusting the executing program's assertion that it
succeeded.

The definition the work supports, and does not exceed:

> ACCL is an experimental system for independently
> evaluating whether computational results and supplied
> execution artifacts satisfy explicitly declared contracts,
> while distinguishing verified evidence from unsupported
> execution claims.

## How it was built

Three implementations, in sequence, each answering defects
in the last — the sequence is part of the record:

- **Phase 7.1** (two independent implementations, one built
  on the Strix, one on the project VM): strict execution
  contracts and a two-axis verifier — computational verdict
  separate from execution provenance. Established: a valid
  computation passes; tampered output fails; a substituted
  contract is detected against a trusted digest; provenance
  is INDETERMINATE without attestation, and a receipt
  claiming hardware execution changes nothing.
- **Phase 7.2 / 7.2C**: receipts bound to a supplied
  software artifact by digest, under a second trust anchor;
  a third axis, artifact integrity. Independent
  reverification (7.2D) reproduced the verdicts against the
  original evidence without regenerating it, and the
  verification report byte-identically.
- **Phase 7.2E** (semantics audit): found *verdict
  coupling* — a mathematically correct output earned a
  computational FAIL when the bound artifact was altered.
  The audit confirmed the behavior so it could be decided
  against, not discovered later.
- **Phase 7.2.1**: verdict separation implemented and
  validated (7.3A): the altered-artifact case now reads
  computation PASS / artifact FAIL / overall FAIL.
- **Final architecture** (`phase7/` here): a single
  self-contained package implementing the three locked
  decisions, below.

## The three decisions (locked 2026-11-18)

1. **Independent computation.** The verifier implements the
   operation itself. Schemas, canonicalization, and
   cryptographic primitives may be shared; the arithmetic
   being tested may not. (The 7.1–7.2.1 verifiers shared an
   `expected_output` with the executor — a defect this
   decision removes. In the final package the contract
   module contains no arithmetic at all.)
2. **Overflow rejected.** Strict signed-int32 semantics: a
   contract whose inputs would overflow is invalid before
   execution. No silent wraparound; one unambiguous result
   per permitted input.
3. **Verdicts decoupled, acceptance fail-closed.**
   Contract binding, computation, artifact integrity, and
   provenance are separate findings under a formal decision
   table (in `phase7/SPECIFICATION.md`). Overall PASS means
   the evidence package satisfies the implemented checks —
   not that physical execution was authenticated.

## Validation (2026-11-18)

- The final package's 23 tests pass on the project VM and
  on the Strix Halo: the decision table, int32 boundary
  conditions, hand-computed independent vectors (expected
  outputs written literally in the tests), and the
  adversarial suite.
- The reference contract's digest under the final package
  is `7ccd837a…`, identical to the trust anchor established
  by the first implementation — the canonical form carried
  across all three codebases unchanged.
- The historical Phase 7.2 receipt (SHA-256 `40384234…`,
  preserved untouched since 7.2C) verifies under the final
  verifier on the Strix: overall PASS; the altered-artifact,
  altered-output, and forged-hardware-claims variants from
  the 7.2D evidence set produce exactly the decision
  table's verdicts.
- The demonstration's evidence is deterministic: run on two
  machines, it produced byte-identical receipt and report
  files (SHA-256 `a269cb9f…` and `25d35ff1…` on both).
- Package archive as validated on the Strix:
  `ACCL-Phase7.3-final.zip`, SHA-256 `a0f0531e…`.

## What it does not do

No attestation: execution provenance is INDETERMINATE in
every report this system produces, and overall PASS must
never be read as authentication of physical execution. No
signatures, no secure clock, no arbitration records yet —
the frozen specification defines arbitration; this
demonstration does not implement it. One operation, small
vectors, one machine class. The earlier implementations are
preserved in their Strix and VM workspaces as the
development record; this package is the record
implementation.
