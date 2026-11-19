# ACCL Execution Receipt Specification — v0.1

Status: FROZEN — Specification v0.1, signed off by Tony on
2026-11-18, with decisions D1–D5 recorded in Section 13.
This document defines a format and a verification
discipline. It is not an implementation, and nothing in it
has been built yet. Amendments follow the project's rule:
a correction is a new version, never a silent edit. Where a
section describes machinery ACCL already has, it says so and
names it; where it describes machinery that does not exist,
it says that instead.

Normative words are used plainly: MUST marks a requirement a
receipt or verifier has to meet to claim conformance with
this specification; SHOULD marks a strong recommendation;
MAY marks an allowed option.

## 1. Purpose

Most computing systems tell you that an operation succeeded.
This specification investigates whether a system can provide
independently verifiable evidence that an operation
satisfied its declared contract.

The question it operationalises, in the words of the flagship
decision of 2026-11-18:

> Can an independent party establish what an autonomous
> system was instructed to execute, what actually executed,
> where it executed, and whether the result satisfied the
> original contract?

An execution log answers none of that by itself: a log is a
claim written by the party being checked. A receipt under
this specification is a structured claim bound by hashes to
its contract, its artifacts, and its evidence, so that a
verifier who trusts none of the participants can recompute
every binding and state, at a named strength, what the
evidence does and does not establish.

## 2. Scope of v0.1

In scope:

- Executions dispatched by ACCL itself, where ACCL controls
  the contract, the plan, the backend, and the artifacts.
- One receipt per execution request, including requests that
  fail on every attempt. A failure is a fact with a name,
  and it gets a receipt too.
- Verification performed after the fact, from the receipt
  and its referenced artifacts, by a verifier that did not
  participate in the execution.

Out of scope for v0.1 (recorded, not silently dropped):

- Receipts for executions on systems ACCL does not dispatch.
- Real-time verification during execution.
- Signatures and hardware attestation as *produced*
  evidence. Both are defined (Sections 7 and 10) so the
  format does not have to change when they arrive; neither
  is claimed as available.
- Dispute resolution between organisations. The arbitration
  record documents a disagreement; it does not settle one.

## 3. Components and roles

| Component | Responsibility | Exists in ACCL today as |
|---|---|---|
| Execution contract | Defines what is permitted and expected | WorkloadSpec + policy gate (`aacl/core/workload.py`, `aacl/policy/`) |
| Execution identity | Identifies the software, hardware, runtime and artifacts | BackendProfile discovery (`aacl/core/capabilities.py`), artifact hashes, plan ids |
| Execution receipt | Records what happened | Receipt stub + telemetry (`aacl/telemetry/`) — shape only, unsigned, incomplete against this spec |
| Independent verifier | Checks the receipt against the original contract | Does not exist. prove.py's independent reference computation is its prototype, not the verifier |
| Arbitration record | Documents disagreements, failures and unresolved claims | Failure classes and attempt records (`aacl/core/failures.py`) are the raw material; the record itself does not exist |

Three roles appear throughout: the **requester** (issues the
contract), the **executor** (ACCL: plans, dispatches, records),
and the **verifier** (independent; checks). One organisation
may hold several roles, but a verification only counts as
independent if the verifier's code path shares no state with
the executor's and treats every executor-supplied value as a
claim to be recomputed, never as evidence.

## 4. The execution contract

A contract MUST be fixed, and its hash computed, before any
execution it governs. A contract assembled after the fact
can describe anything; the ordering is the discipline.

A contract contains:

- `contract_id` — SHA-256 of the contract's canonical form
  (Section 10).
- The workload: `model_id`, and the input, carried as
  `input_sha256` (the input itself MAY accompany the
  contract, but the hash is what binds).
- The permitted execution space: `allowed_precisions`,
  `local_only`, and any further candidate restrictions the
  policy gate enforces.
- The declared targets: `latency_target_ms`,
  `memory_limit_mb`, `cost_budget`, `optimize_for` — each
  optional, each binding if declared.
- The quality terms, if any: `quality_reference` (a named,
  registered evaluation set) and `quality_max_drift` (the
  maximum acceptable mean score error against it). A drift
  tolerance without a reference to measure against is not a
  quality term; ACCL's contract parser already refuses one,
  and this specification adopts that refusal.
- The **evidence requirement**: the minimum evidence class
  (Section 7) a receipt for this contract must reach, and
  any specific controls it demands. A contract that asks for
  no evidence gets a receipt that establishes little, and
  the receipt will say so.

## 5. Execution identity

Identity answers "where, and by what" at four levels. Every
level is recorded as descriptors plus hashes; a descriptor
without a hash is a claim, a hash without a descriptor is
uninterpretable, and a receipt needs both.

- **Software**: the executor's identity — name, version, and
  source revision (commit) of the ACCL code that planned and
  dispatched the execution.
- **Artifacts**: `model_id` and `artifact_id` (the SHA-256
  of the model artifact, as ACCL already computes it), plus
  the hash of any transformation applied (e.g. a quantised
  derivative names its source artifact and its transform).
- **Hardware**: the executing device as discovered, in the
  BackendProfile sense — backend name, architecture, core
  count, memory figures, and, for accelerators, the device
  class and driver/runtime versions. Discovery happens once,
  at process start, so every receipt a process issues
  describes the same machine.
- **Runtime**: interpreter and library versions that could
  change the result — for ACCL today, the Python version;
  for accelerator backends, the runtime build as well. The
  broken-torch episode of Phase 5 is the standing lesson:
  two environments with the same device name and different
  runtime builds are different executors, and identity that
  cannot tell them apart is not identity.

## 6. The execution receipt

One receipt per request. Field groups:

**Header**
- `receipt_id` — derived per Section 10.
- `spec_version` — "0.1".
- `issued_at` — UTC timestamp of issuance. A timestamp is
  the executor's clock claim, recorded as such; nothing in
  v0.1 treats it as proven.
- `status` — "unsigned" in every v0.1 implementation; the
  `signature` field is present and null. (Inherited from the
  existing stub, deliberately: a stub is a promise about the
  record's shape, not about its authenticity.)

**Contract binding**
- `contract_id`, `plan_id`, `request_id` — the hashes and
  ids that tie this receipt to the contract it answers and
  the plan that was chosen under it, including the plan's
  stated `reason` and ranked candidate list, so a verifier
  can check the executed candidate was a permitted one.

**Identity** — the Section 5 record of the executing
environment, as discovered for this execution.

**Execution**
- `executed_candidate` — backend, precision, locality: what
  actually ran, which after a fallback may differ from the
  plan's chosen candidate. The plan is the decision; the
  receipt is the run.
- `attempts[]` — every attempt, in order, each with its
  candidate, outcome (succeeded / failed / denied), failure
  class where applicable (CAPABILITY_LIE, BACKEND_ERROR,
  POLICY_DENIAL, TIMEOUT — the existing four), the backend's
  own detail verbatim, and its duration. Attempts are
  evidence, not diagnosis, and MUST NOT be summarised away:
  a receipt that shows only the successful attempt conceals
  exactly what arbitration exists to examine.
- `fallback` — true if the executed candidate is not the
  plan's first choice.

**Result**
- `output_sha256` — hash of the output as returned.
- `output` — the output itself, inline, when small; for
  large outputs the hash plus a resolvable reference MUST
  stand in its place (Decision D2, confirmed by Tony
  2026-11-18; the size threshold is fixed when the
  demonstration is scoped).
- `quality` — where the contract declared quality terms:
  the measured mean score error and label disagreement rate
  against the named reference, and whether they fall within
  `quality_max_drift`. Measured values, never estimates;
  fields that report estimates MUST be named as estimates,
  as ACCL's plan already names its `estimated_*` fields.

**Evidence**
- `evidence_class` — the class claimed, per Section 7.
- `evidence[]` — the supporting artifacts, each named, with
  its hash and its role: cross-check outputs, control
  outcomes, integrity-check results, telemetry excerpts.
  An evidence entry that cannot be located and re-hashed by
  the verifier is not evidence and MUST NOT be listed.

### Worked example

ACCL's canonical proof run — input [1, 2, 3, 4] through
linear-demo-v1 — as a v0.1 receipt, abridged (values are the
run's real recorded values):

```json
{
  "receipt_id": "<sha256 of canonical body>",
  "spec_version": "0.1",
  "issued_at": "2026-11-17T16:28:09Z",
  "status": "unsigned",
  "signature": null,
  "contract_id": "<sha256 of contract>",
  "plan_id": "ceb756cf0dbea9e4",
  "request_id": "<uuid>",
  "identity": {
    "software": {"name": "aacl", "revision": "<commit>"},
    "artifacts": {"model_id": "linear-demo-v1",
      "artifact_id": "f33ee16f5cbf2d0a458f3cf6730c3b52530af972a1ebd25874cbfceefc5f1351"},
    "hardware": {"backend": "cpu-python", "architecture": "x86_64"},
    "runtime": {"python": "3.12.3"}
  },
  "execution": {
    "executed_candidate": {"backend": "cpu-python", "precision": "fp64", "local": true},
    "attempts": [{"candidate": "cpu-python/fp64", "outcome": "succeeded", "attempt_ms": 0.021}],
    "fallback": false
  },
  "result": {
    "output": {"score": 4.375, "label": 1},
    "output_sha256": "<sha256 of canonical output>",
    "quality": {"reference": "fp64-reference",
      "max_abs_score_error": 1.538403431311508e-06,
      "label_disagreements": 0}
  },
  "evidence_class": "E1",
  "evidence": [{"role": "cross-check", "artifact": "evidence/report.json",
    "sha256": "<hash>", "note": "1000-sample comparison, seed 42, independent fp64 reference"}]
}
```

## 7. Evidence classes

The heart of the specification. A receipt generated by the
executing machine is not automatically proof of physical
execution, so receipts claim a class, classes have
satisfaction rules, and a verdict always states the class it
reached. The classes are cumulative in strength, and a
receipt's class is set by its *weakest* supporting element:
strength claimed beyond the weakest link is a misstatement
the verifier exists to catch.

**Self-reported (E0).** The executor's own record, bound by
content hashes. Establishes: this record existed in this
form when it was hashed, and has not changed since. Does
not establish that the execution happened, happened where
claimed, or produced the recorded output. Every ACCL
telemetry line and receipt stub today is E0.

**Cross-checked (E1).** The result was independently
recomputed by a second implementation or path that shares
no code with the executed one, and compared within the
contract's tolerance. Establishes: the recorded output is
the output the contracted computation produces, whoever ran
it. Does not establish where the original ran. Prototype:
prove.py's float64 reference against the fp32 path (max abs
error 1.54e-06, 0 disagreements over 1,000 seeded samples);
the NPU harness's own NumPy reference against the device
kernel is the same pattern on other hardware.

**Corroborated (E2).** The execution was surrounded by
controls designed to catch substitution, silent fallback,
and environment lies: pre-registered environment checks that
must pass before the run counts; introspection of the
operative execution path (the NPU probe recording the active
tensor class — XRTTensor, not the CPU-only fallback the
factory silently substitutes — is the type specimen);
paired negative controls whose failure is expected if the
claimed path is real (the memlock control); structural
integrity checks over protected artifacts before and after
(the Phase 5 leak test's 32 byte-identical files).
Establishes: the claimed path was the operative one, to the
strength of the controls actually run — and the receipt
MUST enumerate those controls, because E2 without an
enumeration is a slogan. Does not establish it beyond the
controls' reach: a control that cannot observe a substitution
does not rule it out.

**Hardware-attested (E3).** A hardware root of trust signs
measurements of the executing code and device state, and
the verifier checks the signature against the hardware
manufacturer's chain. Establishes: the strongest binding
available between a receipt and a physical execution.
**Status in v0.1: defined, not instantiable.** No ACCL
backend produces attestation today; whether the Strix's
firmware TPM can produce usable quotes is an open
investigation, and datacenter attestation (SEV-SNP class)
does not exist on this APU. A v0.1 receipt MUST NOT claim
E3.

Rules applying to all classes:

- A contract MAY require a minimum class. A receipt below
  the contract's minimum is a contract violation even if
  the output is correct — the requester asked for evidence,
  not only for a result.
- A verifier MUST report the class it verified at, which
  may be lower than the class claimed (Section 8).
- Evidence ages: a cross-check or control run at a different
  time, on a different environment identity, supports
  nothing about this receipt. Evidence entries MUST bind to
  this execution's identity and request.

## 8. Verification

The verifier is a program a stranger can run. Given a
contract, a receipt, and the referenced artifacts, it MUST:

1. Recompute `contract_id` and `receipt_id` from the
   canonical forms and compare. Any mismatch ends the
   check: the record being examined is not the record that
   was issued.
2. Check the binding chain: the receipt's plan was chosen
   under this contract; the executed candidate was inside
   the contract's permitted space, or the deviation is
   recorded as an attempt/fallback with its failure class.
3. Re-hash every evidence artifact and confirm it exists as
   hashed.
4. For E1 and above, re-run the cross-check itself from the
   contract's input and the independent reference — not
   read the executor's comparison, recompute it — and
   compare within tolerance.
5. For E2, examine each enumerated control's own record and
   confirm it ran, bound to this execution, with the
   outcome the receipt claims.
6. Check the quality terms, where declared, against the
   measured values.

The verifier issues one verdict, always with its class:

- **VERIFIED** — every check passed at the claimed class.
- **VERIFIED-AT-REDUCED-CLASS** — the record is sound but
  the evidence supports a lower class than claimed. The
  verdict names both classes. This is a downgrade, and it
  generates an arbitration record (Section 9).
- **CONTRACT-VIOLATED** — the execution is established but
  breached the contract: output outside quality bounds, an
  unpermitted candidate executed, evidence below the
  contract's minimum class.
- **NOT-ESTABLISHED** — the evidence does not establish the
  execution at any class: broken hashes, missing artifacts,
  a cross-check that disagrees. NOT-ESTABLISHED is a
  statement about the evidence, not an accusation about the
  execution; the record says which, and does not blur them.

The verifier's output is itself a record — contract id,
receipt id, verdict, class, the checks run and their
outcomes, verifier identity and version — so that a second
verifier can check the first. Verification that cannot
itself be examined is another log.

## 9. Arbitration records

An arbitration record is issued when the record disagrees
with itself or with its checkers:

- A verifier returns VERIFIED-AT-REDUCED-CLASS,
  CONTRACT-VIOLATED, or NOT-ESTABLISHED.
- An execution fails on every attempt (the ExecutionFailed
  case: the attempts are the record's core).
- A CAPABILITY_LIE is recorded — a backend claimed an
  operation and refused it; the claim and the refusal are
  both preserved, and the registry downgrade that followed
  is named.
- Two verifiers disagree about the same receipt.

An arbitration record contains: the contract, receipt, and
verdict(s) in dispute, by hash; the failure class or
disagreement, in the backend's or verifier's own words
where they exist; and a status — RESOLVED-BY-RERUN (a fresh
execution under the same contract produced a verifiable
receipt), RESOLVED-BY-DOWNGRADE (the reduced class or the
failure is accepted as the final record), or UNRESOLVED.
UNRESOLVED is a legitimate terminal state; an arbitration
record that must close will eventually be made to lie.

Arbitration records are append-only, are never edited after
issuance (a correction is a new record referencing the old),
and carry receipt ids of their own: the disagreement is
also an event in the record, receipted like any other.

## 10. Integrity and canonicalisation

- All hashes are SHA-256, as ACCL's artifact ids already
  are. A future version may add algorithms; v0.1 receipts
  name no algorithm because there is exactly one.
- Canonical form: JSON, UTF-8, keys sorted, no insignificant
  whitespace — the derivation the existing receipt stub
  already uses for its identity hash, extended from the
  identity fields to the whole body.
- `receipt_id` is the SHA-256 of the canonical receipt body
  excluding the `receipt_id` and `signature` fields
  (Decision D1, confirmed by Tony 2026-11-18). This
  strengthens the stub's derivation,
  which hashes only plan, artifact, and request: under this
  spec, changing any recorded fact about the run changes
  the receipt's id.
- `contract_id` is likewise the SHA-256 of the canonical
  contract.
- Signatures: the `signature` field is reserved. When a
  signing party exists — an executor key at E0–E2, a
  hardware quote at E3 — it signs the `receipt_id`. Until
  then the field is null and `status` is "unsigned", and no
  text anywhere may describe an unsigned receipt as
  authenticated.

## 11. What exists, and what the demonstration must add

| Spec element | State today |
|---|---|
| Contract (WorkloadSpec, policy gate) | Exists; needs `contract_id` hashing and the evidence-requirement field |
| Identity (BackendProfile, artifact hashes) | Exists; needs the software-revision and runtime-build fields recorded per receipt |
| Receipt | Stub exists (5 fields); the Section 6 schema is mostly new assembly from existing records — plans, attempts, telemetry already carry the facts |
| Evidence E0 | Exists (telemetry, stubs) |
| Evidence E1 | Exists as prove.py's pattern; needs generalising from the proof harness to arbitrary executions |
| Evidence E2 | Patterns proven in sessions (Phase 5 leak test, NPU controls); not assembled into a receipt before |
| Evidence E3 | Defined only; hardware investigation open |
| Verifier | Does not exist — this is the demonstration's core build |
| Arbitration record | Raw material exists (failure classes, attempt records, downgrades); the record format is new |

The honest summary: the specification mostly *assembles*
facts ACCL already records and disciplines them with hashes,
classes, and an independent checker. The genuinely new
engineering is the verifier and the E2 assembly.

## 12. Limitations and nonclaims

- Below E3, a receipt is evidence, not proof. E0–E2 raise
  the cost of a false record and catch whole classes of
  accident and substitution; a determined executor who
  controls the machine and fabricates every artifact
  consistently defeats them, and this specification does
  not claim otherwise.
- A VERIFIED verdict certifies that the contracted
  computation ran within its declared bounds. It does not
  certify that the model is good, the contract was wise, or
  the output should be acted on.
- Cross-checks inherit their reference's limits: an E1
  check against a reference implementation establishes
  agreement with that reference, and where the reference is
  itself the definition of correct (as in prove.py), the
  receipt says so.
- Timestamps are claims. Ordering between receipts from one
  executor is established by hash binding, not by clocks.
- The failure classes are four because ACCL has met four.
  A backend that fails in a way none of them names will be
  recorded as BACKEND_ERROR with its detail verbatim, and
  the class list will grow by amendment, not by stretching.

## 13. Decisions

All five were put to Tony one at a time, in the order they
bite, and decided on 2026-11-18:

- **D1 — Receipt id derivation. DECIDED (Tony, 2026-11-18):**
  the full-body hash (Section 10), superseding the stub's
  identity-fields hash. Two receipts with different recorded
  attempts can no longer share an identity.
- **D2 — Output carriage. DECIDED (Tony, 2026-11-18):**
  inline when small; hash plus a resolvable reference when
  large. The size threshold is fixed when the demonstration
  is scoped.
- **D3 — Arbitration in v0.1. DECIDED (Tony, 2026-11-18):**
  the arbitration record format stays in v0.1, as drafted
  in Section 9. Failures already produce its raw material,
  and the first downgrade or total failure the demonstration
  meets will need the format defined, not improvised.
- **D4 — Class names. DECIDED (Tony, 2026-11-18):** the
  names lead — Self-reported, Cross-checked, Corroborated,
  Hardware-attested — written with the code on first use
  ("Corroborated (E2)") in the spec and all public text;
  the code alone is the machine value in the receipt's
  `evidence_class` field. Section 7's headings follow this
  form.
- **D5 — The demonstration's headline class. DECIDED
  (Tony, 2026-11-18):** the runnable demonstration
  (deliverable 2 of the flagship decision) will issue a
  Corroborated (E2) receipt — cross-check plus enumerated
  controls — as its headline artifact. Cross-checked (E1)
  is prove.py's existing pattern; E2 is the class the
  programme's session work has been rehearsing, and it is
  the demonstration's build target.

— End of Specification v0.1 —
