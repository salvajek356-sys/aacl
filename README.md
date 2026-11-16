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

## Layout

```
aacl/
  core/          WorkloadSpec, BackendProfile, execution types
  planner/       candidate generation, scoring, plan assembly
  policy/        the independent policy gate (rules + engine)
  backends/      backend contract + CPU reference backend
  optimization/  transformation services (quantization — Phase 4)
  telemetry/     event metrics + JSONL recorder
  models/        model registry and artifact identity
  api/           Runtime + POST /infer
prove.py         runs the tests and regenerates evidence/ (venv required)
test_aacl.py     the v0.1 proof's tests, unmodified
```

## Run the proof

```sh
python3 -m venv .venv
.venv/bin/python prove.py
```

Standard library only. No installation, model download, credentials, or
network service required.
