# The Strix NPU — an enablement track, not a phase

Recorded 2026-11-17. The Strix Halo sessions numbered 6.1–6.7A in
their own logs brought the machine's NPU from undiscovered to
compiler-ready. They are recorded here as what they are: a
hardware enablement track, parallel to the numbered phases, not
one of them. ACCL's phases keep the meanings the plan gave them
(Phase 6 is measured, adaptive planning; the governance work
follows it). An NPU backend, if one is ever scoped and built,
will take its phase number then — and the planner will meet the
device the way it met the GPU: as a profile the discovery probe
has verified, behind the same backend line, with nothing above
that line changed.

## What the sessions established

- Hardware: AMD XDNA NPU at PCI 0000:c7:00.1 (1022:17f0 rev 11),
  enumerated by XRT as RyzenAI-npu5, 8 columns, firmware
  1.1.2.65, kernel driver amdxdna, device /dev/accel/accel0.
- Runtime: XRT 2.21.75 from Ubuntu's packages (libxrt2,
  libxrt-npu2, libxrt-utils, libxrt-utils-npu, python3-xrt). The
  vendor validation archive was fetched from Xilinx's VTD
  repository, hash-verified (SHA-256 57384f0d…), and installed at
  the user level.
- Execution: the vendor INT8 GEMM validation passed twice at
  51.0 TOPS in Default power mode (logs 9a0ea452…, 4ff40154…) —
  AMD's own kernel, at the part's rated figure. No custom program
  has been compiled or run yet.
- Compiler: IRON / MLIR-AIE v1.4.5 (source at commit 86ca39d3;
  wheel SHA-256 6a6e5c3a…) with the pinned Peano compiler
  (llvm-aie 22.0.0.2026102001+4f5df13d), installed in the isolated
  venv ~/accl-iron-research/ironenv. Compiler startup 6/6,
  runtime initialization PASS, and a clean-room verification
  (session 6.7A) with explicit install directories: PASS.
- Python access: pyxrt imports in the system python, and inside
  a venv when /usr/lib/python3/dist-packages is appended to
  sys.path; device enumeration and identity queries verified
  from Python.

## Standing constraints of this machine

- Memory lock: the default memlock limit (8 MiB) is below XRT's
  64 MiB locked-memory request, so every XRT process fails before
  it starts unless its limit is raised. All sessions used a
  temporary per-process raise (prlimit to 256 MiB); no persistent
  limits change has been made. Under this project's discovery
  design, that failure reads as "NPU absent" — an exit with an
  error, not a crash — and the CPU serves on.
- The interactive shell carries a ROS PYTHONPATH
  (/opt/ros/lyrical) that contaminates bare python and pip
  invocations; the sessions unset it throughout, and any future
  NPU work here must do the same.
- AMD's env_install.sh requires python3.12 exactly; it was
  bypassed, deliberately and on the record, in favor of the
  release's cp314 wheel on the machine's python 3.14.
- `pip check` flags llvm-aie as "not supported on this platform":
  its wheel metadata declares cp310 tags while its filename
  declares py3-none. The binaries are verified native x86-64 ELF
  and run; it is a packaging-metadata mismatch, not a defect, and
  it will not go away by reinstalling.

## The boundary

Nothing in ACCL references the NPU. Discovery does not probe for
it, the planner has never seen its profile, and no model has run
on it. The standing next step, when it is taken, is the IRON
vector-addition example — it JIT-compiles, executes on the
device, and verifies itself against NumPy — the NPU's equivalent
of the GPU's first dispatched kernel.

## Addendum (2026-11-17, session 6.7B) — first compiled program

The standing next step above has been taken. The upstream
vector-addition example (INT32, 32 elements, source SHA-256
d73c5d17…, unmodified) was compiled from its IRON Python source
and executed on the device under the clean configuration of
session 6.7A; the example's own comparison against NumPy
reported PASS and the process exited 0 (execution log SHA-256
c4624494…). The boundary that remains is the one that matters:
this was the toolchain's example, not ACCL code — discovery
still does not probe for the NPU, and no ACCL model has run on
it. An NPU backend remains a decision to scope, not a fact to
record.

## Addendum (2026-11-17, session 6.7C) — repeatability

The unmodified example ran five consecutive times under the
raised limit: 5/5 PASS, each exit 0 (evidence directory
vector-add-verify-6.7c.ziStlsmu; per-run logs hashed in the
session record). The paired control — the identical command
without the memlock raise — failed with exit 1, and the failure
stage is classifiable from its traceback: tensor construction →
acquire_device() → pyxrt.device(index). The failure sits in the
XRT/device layer, at device acquisition, before any compilation
or execution. Under the interpretation fixed in advance, that
supports dependence on the NPU runtime; it is not, by itself,
proof of physical execution, and the record does not claim it
as such. Remaining before any ACCL integration (Tony's gate):
the scale sweep (6.7D) and the controlled-input independent
comparison (6.7E).

## Addendum (2026-11-18, sessions 6.7D and 6.7E) — scale, controlled inputs, gate closed

These two sessions were run by Muse over SSH, at Tony's
direction, under a narrow passwordless rule he granted for the
purpose (prlimit with exactly the 256 MiB memlock value used
throughout this track, wrapping runuser to his own account;
nothing runs as root). The scripts were the ones prepared for
the sessions in advance; the example and both repositories are
unchanged, as in every prior session.

6.7D, the scale sweep: the unmodified example ran at n = 32,
256, 1024, 4096, 16384, 65536, 262144, and 1048576, each size in
its own process with its own timeout — 8/8 PASS, exit 0, no
failing size in the swept range. Wall time per size was
0.50–0.67 s and is labeled compile-inclusive; it is dominated
by process startup and JIT work, not kernel time. (The
non-verbose logs are exactly "PASS!\n", six bytes, so their
identical hashes are expected, not anomalous.) A verbose
spot-check at n = 1048576 showed real inputs, correct sums in
the printed window, and the example's full-vector PASS.
Evidence directory vector-add-sweep-6.7d.1CqUNMAy; sweep
summary SHA-256 806a42ca….

6.7E, the controlled-input comparison: the session opened with
its API gate. iron.tensor passes an ndarray and device through
to the tensor factory, and the probe recorded the active
tensor class as aie.utils.hostruntime.xrtruntime.tensor.
XRTTensor — the XRT-backed class, not the CPU-only fallback
the factory can silently substitute when XRT cannot be probed.
The harness then imported the unmodified example's own kernel
and called it with fixed tensors of its own construction,
saving and hashing the inputs before any device work, with the
verdict resting on the harness's own NumPy comparison: zeros,
sequential, negatives, large-in-range, and a seeded random
case at 4096 elements — all exact, zero mismatches, the
example's assert_pass concurring as second opinion in every
case. An exploratory int32-overflow case also matched NumPy's
wrapping arithmetic exactly; it is recorded, not counted. The
paired control ran the seeded case without the memlock raise
on hash-identical inputs and failed with exit 1 at the 64 MiB
locked mmap (EAGAIN) — the XRT/device layer under the
interpretation fixed in advance: it supports dependence on
the NPU runtime and is not, by itself, proof of physical
execution. Evidence directory controlled-verify-6.7e.
nPorGPj9.

With 6.7D and 6.7E, every item on the verification gate fixed
before integration is satisfied: execution of the unmodified
example (6.7B), repeatability (6.7C), the runtime-dependency
control (6.7C, 6.7E), scale (6.7D), independent controlled-input
correctness (6.7E), and hashed, reproducible artifacts
throughout. The boundary that remains is unchanged and is the
point of the gate: no ACCL code has touched the NPU. An
isolated backend prototype exposing only validated operations
(Tony's 6.7F) is now the next decision, not a fact recorded
here.
