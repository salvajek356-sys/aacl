# ACCL — Final Verification Architecture: Three Design Decisions

Decided by Tony, 2026-11-18. These decisions govern the final
verifier revision and the candidate for external reproduction.
They resolve the three design questions raised in review of
the Phase 7.1 / 7.2 implementations (Muse's VM workspace and
the externally built Strix packages).

## Decision 1 — Independent computation

The verifier must independently implement the contract's
mathematical operation. It must not import the executor's
arithmetic, nor share an implementation with it (the Phase 7.1
package's shared `expected_output` in the contract module is
the defect this removes). Schemas, canonicalization rules,
and cryptographic primitives may be shared; the computational
implementation being tested may not.

Qualification (Tony's): separate implementations reduce
correlated defects; they do not eliminate common
specification errors. Independent test vectors and
boundary-condition tests are still required.

Component responsibilities:

| Component | Responsibility |
|---|---|
| Contract parser | Validate the authorized operation and inputs |
| Executor | Execute the requested computation |
| Independent verifier | Independently calculate the expected result |
| Receipt evaluator | Compare evidence against the trusted contract |
| Verdict generator | Report separate findings |

## Decision 2 — Integer overflow is rejected

Phase 7.1's strict signed-int32 semantics are retained:
`vector_add_int32`, verification `exact`, overflow
**forbidden**. If adding two inputs exceeds the signed
32-bit range, the contract is invalid and is rejected before
execution. No silent wrapping (e.g. 2147483647 + 1 does not
become -2147483648 under this contract). The contract thereby
defines one unambiguous mathematical result for every
permitted input. Modular arithmetic, if ever wanted, gets a
separate operation with explicit wrapping semantics; the
meaning of the existing operation is not changed silently.
(This reverses the wrap semantics in Muse's VM
implementation.)

## Decision 3 — Verdicts are decoupled; acceptance is fail-closed

Computational correctness and software artifact integrity
are separate findings, reported on separate axes, with an
overall verdict derived by the decision table below. A
mathematically correct result from an untrusted artifact
reports COMPUTATIONAL_VERDICT: PASS and ARTIFACT_INTEGRITY:
FAIL — computational FAIL is never used as a substitute for
artifact FAIL. When missing or untrusted prerequisites
prevent evaluation of a dimension, that dimension remains
INDETERMINATE.

| Contract | Computation | Artifact | Provenance | Overall |
|---|---|---|---|---|
| PASS | PASS | PASS | INDETERMINATE | PASS* |
| PASS | PASS | FAIL | INDETERMINATE | FAIL |
| PASS | FAIL | PASS | INDETERMINATE | FAIL |
| FAIL | INDETERMINATE | INDETERMINATE | INDETERMINATE | FAIL |
| PASS | PASS | INDETERMINATE | INDETERMINATE | FAIL |

\* Overall PASS means the evidence package satisfies the
currently implemented integrity and computational checks. It
does not mean that physical execution has been
authenticated. For future systems requiring attestation, an
additional acceptance profile will be defined under which
provenance must also pass — rather than silently changing
the meaning of an established verdict.

## The five principles

1. **Independent computation** — the verifier does not reuse
   the executor's arithmetic implementation.
2. **Strict contracts** — unsupported or overflowing
   operations are rejected.
3. **Independent evidence dimensions** — each verdict
   describes its own verification result.
4. **Fail-closed acceptance** — missing required evidence
   prevents overall acceptance.
5. **Explicit uncertainty** — unauthenticated execution
   claims remain indeterminate.

## Definition

> ACCL is an experimental system for independently evaluating
> whether computational results and supplied execution
> artifacts satisfy explicitly declared contracts, while
> distinguishing verified evidence from unsupported execution
> claims.

This statement is supported by what has been demonstrated.
It does not claim execution attestation has been solved.

## Sequence (Tony's order)

1. **Phase 7.3A** — validate the existing Phase 7.2.1
   verdict-separation package on Strix Halo, establishing
   that the coupling defect is fixed without disrupting
   previous evidence. (The 7.2.1 package still imports
   `expected_output` from the original contract module —
   Decision 1 is not yet implemented there.)
2. **Final verifier revision** — independent arithmetic,
   strict overflow checks, expanded adversarial tests.
3. **Package the complete independent demonstration** for
   someone who has never seen the research — the candidate
   for external reproduction, not another open-ended
   experiment.
