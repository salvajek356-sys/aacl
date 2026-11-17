# Phase 5 on the Strix Halo — the leak test session

Phase 5 was built on a machine with no GPU. Everything that could be
built and verified there was: the GPU backend, honest discovery, the
registration seam, the demo, and a mechanical diff audit. What could
not happen there is the point of the phase: the backend running on a
real device, chosen by the unchanged planner, checked against the CPU.

This runbook is that session. The pass/fail criteria are stated in
advance, below, before any output exists. Run the steps in order; if a
step says stop, stop — a stopped session with a clear report is a
result, and an improvised one is not.

**Environment facts (known in advance):** Strix Halo (gfx1151),
Ubuntu 26.04.1, system Python 3.14.4. ROCm PyTorch is available in the
environment where the Emerson work runs (TheRock gfx1151 wheels). Use
*that* interpreter and environment for everything below — the one where
torch already works. Do not install anything for this session.

**The commit:** Phase 5 is the commit titled "Phase 5: GPU backend +
the leak-test pack (GPU run pending)" in the aacl repo — resolve its
hash on either machine with
`git rev-list -1 --grep='^Phase 5: GPU backend' main`.
It reaches this machine from the public GitHub repo
(salvajek356-sys/aacl) after Tony's separate push approval — if the
commit is not on GitHub yet, the session waits for the push.

## Criteria, stated in advance

The leak test PASSES only if all of these hold:

1. The test suite is green on the Strix (53 tests; the three
   Phase5GPUTests run — not skip — and pass).
2. The diff audit passes: every change since Phase 4 (commit
   19701d54c5676c4d8b948ba284ef69a26bda2145) is inside its allow-list,
   and the planner, scorer, executor, policy engine, workload
   contract, telemetry shapes, and receipt are byte-identical.
3. The demo's verdict is PASS: the planner selects the GPU for at
   least one workload in the fixed set and the CPU for at least one
   other, and every CPU/GPU cross-check agrees (labels exactly,
   scores within fp32 tolerance).
4. prove.py's precision block is unchanged: max abs error
   1.538403431311508e-06, 0 label disagreements.

Anything else is a finding, and the finding is the result: a red suite,
a failed audit, a demo PARTIAL because one backend honestly dominates
the static estimates, cross-checks that disagree — each says something
specific about the design, and each gets pasted back whole, not
summarized away.

## Step 0 — probe the torch environment (stop conditions live here)

With the interpreter where your Emerson torch works:

```sh
python3 -c "import torch; print('torch', torch.__version__); print('hip', torch.version.hip); print('cuda available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"
```

Expected: a torch version, a HIP version (this is ROCm), `cuda
available True`, and the Strix Halo's device name.

**If torch does not import, or no device answers: STOP.** Paste back
what the probe printed and end the session. Do not improvise installs,
do not try a different torch, do not proceed CPU-only and call it the
session — discovery honestly finding nothing is itself reportable, but
it is not the leak test.

## Step 1 — get the Phase 5 commit

```sh
git clone https://github.com/salvajek356-sys/aacl.git aacl-phase5
cd aacl-phase5
git checkout $(git rev-list -1 --grep='^Phase 5: GPU backend' main)
git log --oneline -3
```

(Or `git pull` an existing clone and check out the same commit.) The
top commit must be the Phase 5 commit named above.

## Step 2 — run the suite

Use the torch-capable interpreter throughout (the suite itself is
stdlib-only; the GPU tests need torch importable and a device present
to run rather than skip):

```sh
python3 -m unittest test_aacl 2>&1 | tail -5
```

Expected: `Ran 53 tests` and `OK` — with **no** `(skipped=3)`: the
three GPU tests must have run. If they skipped, discovery found no
device in this process — go back to Step 0's output and treat the
session as stopped there.

## Step 3 — run the diff audit

```sh
python3 phase5_diff_audit.py
```

Expected: `PASS`, exit code 0, every changed path listed as allowed.
This needs no torch and no venv; it only reads git.

## Step 4 — run the demo

```sh
python3 phase5_demo.py
```

Expected: two discovered profiles (cpu-python and gpu-rocm); the
fixed request set choosing the GPU for the fp64-under-a-tight-target
and iris latency workloads and the CPU for the no-target, fp32, and
small-memory ones (the exact split follows the static estimates — what
matters for criterion 3 is that each backend is chosen at least once);
four cross-checks, all agreeing; verdict `PASS`.

## Step 5 — re-run the proof

prove.py insists on a virtual environment; give it one that can still
see the system torch:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python prove.py 2>&1 | grep -A4 synthetic_precision_comparison
```

Expected: `max_absolute_score_error: 1.538403431311508e-06` and
`label_disagreements: 0`. (prove.py's own requests declare no targets,
so the standing preference keeps them on the CPU reference path; if
the numbers move anyway, that is a finding — paste it back.)

## What to paste back

One message with all of it, verbatim:

1. The Step 0 probe output.
2. The suite's last lines (test count and OK/skips).
3. The full diff audit output.
4. The full demo output, verdict line included.
5. prove.py's precision block.

With those five, the phase can be closed from the other side: guide
and README updated to record the verdict — whichever way it lands —
and the record published. Until then, Phase 5's status is exactly:
**built, not yet run on GPU hardware.**

## Addendum — 2026-11-17: the session ran

The session above was run on 2026-11-17, with two packaging
deviations from the script as written, recorded here rather than
smoothed over: the Phase 5 commit was resolved on GitHub's main
directly (the snapshot push carries no per-phase commit message to
grep for), and Step 3's audit — which diffs against the local
Phase 4 commit — was replaced on the clone by a hash check of the
32 protected files against their Phase 4 blob SHAs, with identical
substance for the protected set.

Results against the criteria stated in advance:

1. Suite green with GPU tests running — **NOT MET.** The suite died
   silently: discovery's in-process probe crashed the process.
2. Protected files unchanged — **MET** on the hardware, by the hash
   check: 32/32 byte-identical to Phase 4.
3. Demo verdict PASS — **NOT MET.** The demo segfaulted in the probe.
4. prove.py precision unchanged — **NOT REACHED** (the same crash).

Diagnosis (Phases 5.1A–5.1F; controlled, read-only): torch-only
fp32 and fp64 device snippets segfault identically — the fault is
not ACCL's and not precision-specific. The same ctypes memory test
(enumerate, allocate, memset, synchronize, free) passes completely
against the system ROCm runtime and dies at hipMemset against the
wheel's bundled HIP runtime. A GDB backtrace places the crash
inside the wheel's bundled HSA runtime: queue creation fails
against the system kernel, and its cleanup path
(ReleaseQueueMainScratch) segfaults on uninitialized state — the
runtime could not even fail cleanly. Hardware, kernel driver, and
system ROCm are exonerated by the controls.

**Verdict: NOT a pass.** The structural leak test passed on
hardware; execution is untestable on this torch build — an
environment finding, not a leak.

Amendment (same day): the discovery probe now runs in a subprocess
(`aacl/backends/gpu.py`, run as `__main__`), so a backend whose
runtime crashes on contact degrades to absent instead of killing
the host. Expected behavior of a re-run on the Strix as it stands:
the suite completes with the GPU tests skipped (the probe child
dies; the GPU is honestly absent), the demo completes CPU-only, and
prove.py runs — the runtime surviving a broken device runtime is
the amendment's own test. Criteria 1, 3, and 4 in their original
form still wait on a torch environment on the Strix that can
dispatch a kernel.

## Closure addendum (2026-11-17) — VERIFIED PASS

The criteria as originally scored above stand as the record of the
first session. They were subsequently met in full:

1. Suite green with GPU tests running — MET (5.2E validation copy:
   53 tests OK, skipped=2 by design; and, after the push, the
   canonical code on the Strix: 60 tests OK, skipped=2, under the
   compat python).
2. Protected files unchanged — MET (32/32, first session).
3. Demo verdict PASS — MET (5.2E: each backend chosen at least
   once; cross-checks 0 / 0 / 1.78e-15 / 9.54e-07, labels exact).
4. prove.py precision unchanged — MET (5.2G.1, run from the repo
   root: 1.538403431311508e-06, 0 disagreements, internal suite
   green).

Environment: isolated venv ~/accl-rocm-compat, torch
2.12.0+rocm7.14.1 from AMD's official multi-arch index
(torch[device-gfx1151]); the user-site 7.1 install and system ROCm
untouched. Fixes validated in a copy and committed: ca9c3dd
(test), bfb80f6 (demo). The amendment (361b580) and both fixes
were pushed (GitHub 12a19601) and pulled on the Strix for the
confirmation below.

Amendment confirmation (2026-11-17, against the pushed code):
under the compat python, 60 tests OK (skipped=2) with the GPU
tests running; under the old user-site python, the suite
completed CPU-only instead of dying in discovery — with one
failure, test_the_real_child_answers_cleanly_on_this_machine,
which asserted the probe child always exits 0. On the broken
runtime the child dies by SIGSEGV (-11), which is the design
working; the test had modeled two of a machine's three torch
states (absent, working — not broken). Corrected in the closure
commits to the contract the parent actually keeps: a clean answer
is believed exactly as given; a dead child means no GPU profile.

Process note: the first prove.py reproduction (5.2G) reported a
hollow PASS from an empty directory — prove.py discovered tests
relative to the caller's working directory, ran zero, and still
printed success. The run was caught and re-done from the repo
root (5.2G.1). The flaw is fixed in the closure commits:
discovery and the evidence directory are anchored to prove.py's
own directory, verified from both the repo root and an empty
directory (60 tests, precision identical either way).
