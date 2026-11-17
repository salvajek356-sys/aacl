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
(scope: Phases 0–4, decided 2026-11-16).

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

## Layout

```
aacl/
  core/          WorkloadSpec, BackendProfile, execution types
  planner/       candidate generation, scoring, plan assembly + explanation
  policy/        the independent policy gate (rules + engine)
  backends/      backend contract (async handles) + CPU reference backend
  optimization/  transformation services (quantization — Phase 4)
  telemetry/     event metrics + JSONL recorder + receipt stubs
  models/        model registry and artifact identity
  api/           Runtime + POST /infer
prove.py         runs the tests and regenerates evidence/ (venv required)
test_aacl.py     the v0.1 proof's tests, unmodified, plus Phase 1 tests
```

## Run the proof

```sh
python3 -m venv .venv
.venv/bin/python prove.py
```

Standard library only. No installation, model download, credentials, or
network service required.
