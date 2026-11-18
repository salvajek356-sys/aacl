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
