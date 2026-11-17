# AACL — Agentic Acceleration Compatibility Layer

A compatibility runtime: applications submit a typed **WorkloadSpec**; the
runtime inspects what the machine can actually do, generates candidate plans,
removes the infeasible and the forbidden, scores what remains explainably,
executes, and records telemetry for every run.

**New here?** Read [the reader's guide](docs/guide.md) first — what this is,
why it exists, and where it honestly stands, in plain language.

Design sources, in order of authority:

1. *ACCL: Finishing the Thought Experiment* — the revision layer (target-pressure
   scoring, fallback protocol, artifact identity, measured quality, M10–M12).
2. *From Concept to Working Runtime* (ACCL2) — the original roadmap, M0–M10.
3. The v0.1 architecture proof — the working baseline this repo grows from.

Plan of action: `~/workspace/your_files/accl-plan/accl-plan-of-action.md`
(scope: Phases 0–4, decided 2026-11-16; Phase 5 approved 2026-11-17).

## Status

**Phase 0 complete (2026-11-16).** The v0.1 proof was ported from its single
file into the package layout below with behavior unchanged — proven, not
asserted: the proof's own test file and proof script run unmodified, 12/12
tests pass, and the synthetic precision comparison reproduces the original
packaged evidence exactly (max abs error 1.538403431311508e-06, 0 label
disagreements). The original proof zip remains untouched as the baseline record.

**Phase 1 complete (2026-11-17).** Contracts v2. WorkloadSpec accepts a
latency target, a memory limit, a cost budget, `optimize_for`, and a
`quality_reference` — each validated (invalid values are typed refusals),
carried into the plan, and named in its explanation, but *not yet scored
against*: target-pressure scoring is Phase 2, quality measurement Phase 4,
and the explanation says so in plain words. Execution goes through the async
handle contract (`submit()` → `result()` / `cancel()` / optional `stream()`);
the CPU backend completes trivially and says so. Artifact identity is the
generalized content address `hash(model_id, source_digest, precision,
transform_version, backend_constraints)`, canonically encoded. Telemetry
splits `load_ms` / `init_ms`; every response carries the plan explanation and
an unsigned receipt stub (signature null, status `"unsigned"` — a stub, not
cryptography). 17/17 tests pass — the 12 proof tests unmodified, 5 new
Phase 1 tests including plan determinism — and the precision evidence is
unchanged: max abs error 1.538403431311508e-06, 0 label disagreements.

**Phase 2 complete (2026-11-17).** Planning for real. Capability discovery
is real: the backend profile is read from the machine at startup — usable
cores, total and available memory, and a cache ceiling (`max_cache_bytes`,
a quarter of total memory) — and the precision list is exactly what the CPU
backend implements. Each candidate gets static capability estimates
(latency, memory, cost — fields named `estimated_*`, the model and its
constants in `planner/estimates.py`), and selection is target-pressure
scoring: the lowest worst pressure against the workload's declared budgets
wins; epsilon ties break by `optimize_for`, then absolute estimated cost,
then backend name, then artifact id; every scored plan explains itself in
the "76% of its latency budget" form. Quality remains unmeasured — a
declared `quality_reference` contributes no pressure and the explanation
says so — and a request with no budgets keeps the standing precision
preference, there being no pressure to score. 23/23 tests pass (the 12
proof tests unmodified; one Phase 1 test adapted where the scorer's
replacement changed the targeted request's selected precision, with the
reason recorded in the test itself) and the precision evidence is
unchanged: max abs error 1.538403431311508e-06, 0 label disagreements.

**Phase 3 complete (2026-11-17).** Fallback protocol + artifact lifecycle.
The plan carries the ranked survivor list; the executor tries candidates in
rank order, re-gates policy per attempt, bounds attempts (the ranked list,
capped at 8), and records every attempt — candidate, artifact, outcome,
failure class, timing — in the response and the JSONL telemetry. Failure
classes are named: `CAPABILITY_LIE`, `BACKEND_ERROR`, `POLICY_DENIAL`,
`TIMEOUT`. A capability lie (a backend rejects an operation it claimed)
downgrades the registry entry for that backend/model/precision; the next
plan deprioritizes it — never excludes it — and its explanation says so.
Total failure raises a typed `ExecutionFailed` naming every attempt. The
`ArtifactCache` stores artifacts by their generalized identity under
`get_or_build`, evicts LRU within `max_cache_bytes`, and never evicts
pinned entries; the runtime resolves a plan's artifacts into the cache and
pins them for the request. The receipt names what actually ran. Proved by
fault injection: a test backend that claims fp64 then rejects it produces
an advance to fp32, per-attempt records, and a next plan that avoids fp64.
33/33 tests pass (all 23 prior tests unmodified, 10 new) and the precision
evidence is unchanged: max abs error 1.538403431311508e-06, 0 label
disagreements.

**Phase 4 complete (2026-11-17).** Quantization + measured quality. A
second model is installed: `iris-logreg-v1`, multinomial logistic
regression genuinely trained in-repo on the embedded Iris dataset (90
train rows, full-batch gradient descent, frozen recipe; `train_iris.py`
retrains it and reproduces the committed weights exactly; fp64 accuracy
on the held-out eval split is 29/30). The transformation service
(`optimization/quantization.py`) owns calibration: it runs the 30-row
calibration split, derives per-tensor symmetric scales, and produces an
int8 artifact (transform version `int8-v1`, its own generalized identity)
that the CPU backend genuinely executes — quantized inputs, integer
accumulation, one dequantizing multiply. Drift against the named
reference `iris-eval-v1` (the 30-row eval split) is measured per
candidate (`optimization/quality.py`), carried on the plan, and recorded
in telemetry per run: fp32 mean score error 5.2e-07, int8 0.0492 (max
0.1846), label disagreements 0 for both — so the new validated
WorkloadSpec field `quality_max_drift` is defined on mean score error,
the figure that moves. With a reference and a tolerance, quality pressure
joins the minimax (loose tolerance + tight latency selects int8; tight
tolerance selects fp32); with a reference alone, drift is reported and
ranks `optimize_for=quality` ties; with no reference, the explanation
prints "quality unmeasured — no reference." Unknown reference names are
typed refusals (`UNKNOWN_QUALITY_REFERENCE`), as is a tolerance with no
reference. int8 is offered only for the trained model — the demo model
has no calibration data, so its `allowed_precisions: ["int8"]` refusal
stands. 44/44 tests pass (the 12 proof tests and all Phase 3 tests
unmodified; four earlier tests adapted where Phase 4's surface genuinely
changed behavior — the Phase 1 targeted fixture and three others — with
reasons recorded in place) and the precision evidence is unchanged:
max abs error 1.538403431311508e-06, 0 label disagreements.

**Phase 5 built (2026-11-17); the Strix session ran the same day —
structural pass, execution blocked by the machine's torch build
(recorded at the end of this section).** The
second backend: `backends/gpu.py` executes both registered models with
PyTorch on the accelerator (ROCm exposes the device through torch's
CUDA surface; the backend names itself `gpu-rocm` or `gpu-cuda` for
what the device actually is), behind the Phase 1 handle contract,
advertising only the precisions its discovery probe genuinely executes
on the device — fp32/fp64, never int8. PyTorch is the project's first
non-stdlib dependency and is isolated to that one module, imported
lazily: without torch, or without a device, discovery registers the
CPU alone, no GPU candidate is ever generated, and behavior is Phase
4's byte for byte. Registration is the seam: `backends/discovery.py`
holds the registered set (one deterministic snapshot per process),
`backends/router.py` dispatches each attempt to the backend its
candidate names, the composition root wires the router as the default
backend, candidate generation enumerates the registry when the passed
profile is registered, and the estimator gains a GPU row of static
constants (launch overhead + device-context allowance + device
bandwidth rate — placeholders, labeled as such, pending Phase 6's
measured corrections). The planner, scorer, executor, policy engine,
workload contract, telemetry shapes, and receipt are byte-identical
to Phase 4 — not as a claim but as a check: `phase5_diff_audit.py`
diffs the tree against the Phase 4 commit and fails outside a minimal
allow-list (it passes). `phase5_demo.py` runs the fixed request set
and cross-checks CPU vs GPU outputs; on a GPU-less machine it reports
PARTIAL, never PASS. 60/60 tests pass here (44 prior — three adapted
to count relative to the registry, reasons in place — 6 Phase 5
tests, 3 GPU-present tests that skip cleanly without a device, and 7
amendment tests below).

**The Strix session (2026-11-17), recorded plainly.** The structural
half passed on the hardware: 32/32 protected files byte-identical to
Phase 4. The execution half could not run: the machine's torch build
(2.12.0+rocm7.1, in the system python's user site) segfaults on the
first dispatched device kernel — in pure torch, with no ACCL code
present — and controlled follow-up diagnosis isolated the fault to
the wheel's bundled HSA runtime, whose queue creation fails against
the system kernel and whose cleanup path then crashes; the identical
memory test against the system ROCm runtime passes completely. An
environment finding, recorded as one: not a leak, and not a pass.
The session also exposed an ACCL-side flaw — discovery probed
in-process, so the crashing backend took the whole runtime down with
it — fixed the same day by amendment: the probe now runs in a
subprocess (`python -m aacl.backends.gpu`), and a backend that
crashes on contact degrades to absent while the CPU serves on. What
remains unverified: the backend executing on GPU hardware — the
planner choosing it, cross-checks agreeing — which waits on a
working torch environment on the Strix. The session, its criteria
stated in advance, and a dated addendum recording all of this are in
`docs/phase5-strix-runbook.md`.

## Layout

```
aacl/
  core/          WorkloadSpec, BackendProfile, execution types, failure
                 classes, the executor
  planner/       candidate generation, scoring, plan assembly + explanation
  policy/        the independent policy gate (rules + engine)
  backends/      backend contract (async handles), CPU reference backend,
                 GPU backend (torch, lazily imported), discovery/
                 registration, and the dispatching router
  optimization/  the transformation service (int8 quantization, calibration
                 owned by the service) + measured quality (drift vs a
                 named reference)
  telemetry/     event metrics + JSONL recorder + receipt stubs
  models/        model registry, artifact identity, reliability, the cache,
                 the trained iris model and its embedded dataset
  api/           Runtime + POST /infer
prove.py         runs the tests and regenerates evidence/ (venv required)
phase5_demo.py   Phase 5 demo: discovered profiles, the fixed request
                 set, CPU/GPU cross-checks, an honest PASS/PARTIAL/FAIL
phase5_diff_audit.py
                 the leak test made mechanical: diff vs the Phase 4
                 commit, failing outside the Phase 5 allow-list
train_iris.py    retrains the Phase 4 model and verifies the committed
                 weights reproduce exactly
test_aacl.py     the v0.1 proof's tests, unmodified, plus Phase 1, Phase 2,
                 Phase 3, Phase 4, and Phase 5 tests (a few earlier tests
                 adapted where later phases genuinely changed behavior,
                 reasons in place)
```

## Run the proof

```sh
python3 -m venv .venv
.venv/bin/python prove.py
```

The runtime core is standard library only. No installation, model
download, credentials, or network service required. The one exception
is the GPU backend (`aacl/backends/gpu.py`), which imports PyTorch
lazily and optionally: on a machine without torch — or without a
device — it simply never exists, and the proof runs exactly as above.
