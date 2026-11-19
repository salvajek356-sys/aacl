# ACCL Phase 7 — Specification (Final Architecture)

Status: implemented and validated 2026-11-18. This is the
demonstration profile of the ACCL Execution Receipt
Specification v0.1 (frozen 2026-11-18), incorporating the
three verification-architecture decisions locked the same
day. Experimental research specification; not a security
attestation standard.

## 1. Execution Contract v0.1

Schema `accl.execution-contract.v0.1`; exact members
`schema`, `contract_id`, `operation`, `inputs`,
`requirements` — unknown, missing, or duplicate members are
rejected (duplicate members are rejected at JSON load, as
are NaN/Infinity constants).

- `contract_id`: 1–128 ASCII alphanumeric, `-`, `_`, `.` —
  a human label, never a trust anchor.
- `operation`: `vector_add_int32` (the only operation).
- `inputs`: exact `a` and `b`, equal length 1–4096, every
  element a signed int32 integer (booleans are not integers).
- `requirements`: exact `output_dtype: int32`,
  `output_length` (equal to the input length),
  `verification: exact`.

**Overflow is forbidden.** If any pairwise sum would leave
the signed int32 range, the contract is invalid and rejected
before execution. There is no wraparound; the contract
defines one unambiguous result per permitted input.

Canonical form: `json.dumps(sort_keys=True,
ensure_ascii=True, separators=(',', ':'), allow_nan=False)`
encoded as ASCII — a project-specific rule, not RFC 8785
JCS. The contract digest is SHA-256 (lower-case hex) over
the canonical bytes, and must reach the verifier through a
channel independent of the contract/receipt pair.

## 2. Execution Receipt v0.2

Schema `accl.execution-receipt.v0.2`; exact members
`schema`, `contract_sha256`, `operation`, `input_sha256`,
`output`, `output_sha256`, `artifact`, `claims`.

- `contract_sha256`, `input_sha256`, `output_sha256`:
  canonical digests binding the receipt to the contract,
  its inputs, and the recorded output.
- `artifact`: exact `name` (a basename) and `sha256` of the
  supplied program file's bytes. A file hash proves identity
  of bytes provided to verification, not that those bytes
  were loaded or executed.
- `claims`: exact `execution_backend`,
  `execution_location`, `hardware_attestation` — strings,
  all untrusted assertions, reported back as
  reported-but-unverified.

## 3. Verification

The verifier shares with the executor only schemas,
canonicalization, and cryptographic primitives. It
implements the operation itself. It checks, in order:
contract validity and trusted-digest binding; receipt
structure and contract/input binding; independent
recomputation and output-digest agreement; artifact byte
identity against the trusted artifact digest and the
receipt.

Findings (each describes only its own dimension):

| Dimension | Values |
|---|---|
| contract_binding | PASS / FAIL / INDETERMINATE |
| receipt_structure | PASS / FAIL / INDETERMINATE |
| computational_verdict | PASS / FAIL / INDETERMINATE |
| artifact_integrity | PASS / FAIL / INDETERMINATE |
| execution_provenance | INDETERMINATE (always, in this version) |

A dimension that cannot be evaluated for missing or
untrusted prerequisites remains INDETERMINATE. An untrusted
contract gates all downstream dimensions to INDETERMINATE.

Overall verdict (fail-closed):

| Contract | Computation | Artifact | Provenance | Overall |
|---|---|---|---|---|
| PASS | PASS | PASS | INDETERMINATE | PASS* |
| PASS | PASS | FAIL | INDETERMINATE | FAIL |
| PASS | FAIL | PASS | INDETERMINATE | FAIL |
| FAIL | INDETERMINATE | INDETERMINATE | INDETERMINATE | FAIL |
| PASS | PASS | INDETERMINATE | INDETERMINATE | FAIL |

(receipt_structure PASS is additionally required for overall
PASS; a structure failure leaves downstream dimensions
INDETERMINATE and the overall verdict FAIL.)

\* Overall PASS means the evidence package satisfies the
currently implemented integrity and computational checks.
It does not mean physical execution has been authenticated.
A future acceptance profile requiring attestation will be
defined separately, without changing the meaning of this
verdict.

## 4. Limitations, stated as rules

- Hashes establish integrity of recorded artifacts. They do
  not prove execution location, hardware identity, or that
  a particular process ran.
- An attacker who controls both a contract and its
  purported independent trust anchor can present a
  self-consistent false task; anchors must be distributed
  independently.
- An attacker who knows the inputs can synthesize the
  expected output without running the claimed code;
  verification establishes agreement with the declared
  operation, not observed physical execution.
- No signatures, secure clocks, device attestation,
  sandboxing, or multiparty arbitration are implemented.
  Nothing in this version may be retroactively described as
  hardware-verified evidence.
