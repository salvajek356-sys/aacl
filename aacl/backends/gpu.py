"""The GPU backend (Phase 5): the second backend, and the leak test's
subject.

It implements the same contract as the CPU reference backend — `submit()`
returning a handle, trivially completed, because the work is synchronous
here too — and it changes nothing above the backend line to do it. The
planner, scorer, executor, policy gate, workload contract, telemetry
shapes, and receipt never learn that this module exists; registration
(backends/discovery.py) and dispatch (backends/router.py) are the whole
interface.

PyTorch is this project's first non-stdlib dependency, and it is isolated
to this module: imported lazily, inside functions, never at module level.
`import aacl`, the CPU path, and the entire test suite work identically
on a machine with no torch installed — the machine this phase was built
on is exactly such a machine. On ROCm builds, torch exposes the device
through its CUDA API surface (torch.cuda), with torch.version.hip set;
this module writes to that surface and names the backend for what the
device actually is — gpu-rocm or gpu-cuda.

Honesty rules, matching the rest of the runtime:

- Discovery is a probe, not a hope. A profile exists only when torch
  imports, a device answers, and a tiny matmul at each advertised
  precision genuinely executes on it. The probe result is cached: one
  snapshot per process, like the CPU profile's.
- The probe runs in a subprocess — this module, run as __main__ —
  never in the host process. A device runtime can fail in ways no
  exception can catch: on 2026-11-17 the Strix Halo's torch build
  segfaulted inside its bundled HSA runtime on the first dispatched
  kernel (the runtime could not even fail cleanly — queue creation
  failed against the kernel, and its own cleanup path crashed), and
  the in-process probe took the whole runtime, CPU path included,
  down with it. In a child process that same crash is just an exit
  status: the GPU is honestly absent, and the runtime goes on serving
  the CPU. A backend that crashes on contact degrades; it does not
  get to be fatal.
- The backend advertises only the precisions the probe executed —
  fp32/fp64 as the device supports them. It does not claim int8: no
  integer artifact runs here, so no int8 candidate is ever generated
  for this backend, and a hand-built int8 plan is refused in writing.
- Execution math mirrors the CPU backend's outputs exactly in shape —
  {"score", "label"} for the demo model, {"scores", "label",
  "label_name"} for the trained one — computed with torch tensors at
  the plan's precision. The CPU backend's step-by-step fp32 rounding is
  *its* discipline, not reproduced here; cross-backend agreement is
  checked by the Phase 5 demo within fp32 tolerance, labels exactly.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from ..core.capabilities import BackendProfile
from ..core.workload import Rejection
from ..models.registry import (artifact_id, get_model, source_digest,
                               transform_version)
from .base import CompletedHandle

_PROFILE_UNSET = object()
_profile_cache = _PROFILE_UNSET

# The child gets time to import torch, initialize a device runtime,
# and execute two tiny matmuls. Sixty seconds is generous on a healthy
# machine and bounded on a broken one: a hung probe is an absent GPU,
# never a hung runtime.
PROBE_TIMEOUT_SECONDS = 60

_PROBE_KEYS = {"name", "architecture", "logical_cores", "runtime",
               "precisions", "local", "total_memory_bytes",
               "available_memory_bytes", "max_cache_bytes"}


def _torch():
    """The one place torch is imported. Lazy and optional by design."""
    import torch
    return torch


def probe_gpu_profile():
    """The GPU's BackendProfile, discovered by probing the device — or
    None, when there is honestly no GPU to describe: torch absent, no
    device answering, or no precision genuinely executing on it. The
    probing itself happens in a child process (see _run_probe_child):
    a child that dies by signal, hangs past the timeout, or answers
    nonsense is the same discovery result stated a different way.

    Cached after the first probe: discovery is a single deterministic
    snapshot per process, as with the CPU profile.
    """
    global _profile_cache
    if _profile_cache is not _PROFILE_UNSET:
        return _profile_cache
    _profile_cache = _profile_from_probe(_run_probe_child())
    return _profile_cache


def _run_probe_child():
    """Run this module as a child process and read its one-line JSON
    answer. The child is launched with this package's root on its
    PYTHONPATH, so it finds the same code the parent imported wherever
    the parent was launched from. Every failure mode — nonzero or
    signal exit, timeout, an unparseable line — returns None: no
    probe result, so no GPU."""
    env = dict(os.environ)
    root = str(Path(__file__).resolve().parents[2])
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (root if not pythonpath
                         else root + os.pathsep + pythonpath)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "aacl.backends.gpu"],
            capture_output=True, text=True,
            timeout=PROBE_TIMEOUT_SECONDS, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except ValueError:
        return None


def _profile_from_probe(data):
    """The child's JSON, held to the probe's own standard before it
    becomes a profile: the full key set, a GPU name, and a non-empty
    precision list drawn from the floating-point pair. A child
    claiming int8 — or anything else this backend never advertised —
    is refused like any other impossible claim."""
    if not isinstance(data, dict) or set(data) != _PROBE_KEYS:
        return None
    if data["name"] not in ("gpu-rocm", "gpu-cuda"):
        return None
    precisions = data["precisions"]
    if (not isinstance(precisions, list) or not precisions
            or not set(precisions) <= {"fp32", "fp64"}):
        return None
    try:
        return BackendProfile(
            name=data["name"],
            architecture=str(data["architecture"]),
            logical_cores=int(data["logical_cores"]),
            runtime=str(data["runtime"]),
            precisions=tuple(precisions),
            local=bool(data["local"]),
            total_memory_bytes=int(data["total_memory_bytes"]),
            available_memory_bytes=int(data["available_memory_bytes"]),
            max_cache_bytes=int(data["max_cache_bytes"]),
        )
    except (TypeError, ValueError):
        return None


def _probe_device():
    """The probe itself — executed only in the child process (see
    _probe_child_main). Returns the profile as a JSON-safe dict, or
    None when there is honestly no GPU to describe: torch absent, no
    device answering, or no precision genuinely executing on it."""
    try:
        torch = _torch()
    except Exception:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        props = torch.cuda.get_device_properties(0)
        precisions = []
        for precision, dtype in (("fp64", torch.float64),
                                 ("fp32", torch.float32)):
            try:
                with torch.no_grad():
                    ones = torch.ones((2, 2), dtype=dtype, device="cuda")
                    (ones @ ones).cpu()
                precisions.append(precision)
            except Exception:
                pass
        if not precisions:
            return None
        hip = getattr(torch.version, "hip", None)
        total = int(props.total_memory)
        return {
            "name": "gpu-rocm" if hip else "gpu-cuda",
            "architecture": str(props.name),
            "logical_cores": int(props.multi_processor_count),
            "runtime": str(torch.__version__),
            "precisions": precisions,
            "local": True,
            "total_memory_bytes": total,
            "available_memory_bytes":
                total - int(torch.cuda.memory_allocated(0)),
            "max_cache_bytes": total // 4,
        }
    except Exception:
        return None


def _probe_child_main():
    """The child's whole job: probe, print one line of JSON, exit. If
    the device runtime kills the process natively, the line never
    prints and the parent reads the exit status instead — which is
    the point of being a child."""
    print(json.dumps(_probe_device()))


class GPUBackend:
    """Executes the registered models with torch on the accelerator.

    Constructed with a discovered profile (see probe_gpu_profile). With
    no profile and no discoverable device it refuses to exist — a
    backend for hardware that isn't there would be a claim, and claims
    are what the probe is for. discover() is the polite constructor:
    an instance, or None.
    """

    def __init__(self, profile=None):
        if profile is None:
            profile = probe_gpu_profile()
        if profile is None:
            raise RuntimeError(
                "GPUBackend requires a device: discovery found none")
        self._profile = profile

    @classmethod
    def discover(cls):
        profile = probe_gpu_profile()
        return cls(profile) if profile is not None else None

    def capabilities(self):
        return self._profile

    def submit(self, selected, values):
        try:
            return CompletedHandle(output=self._run(selected, values))
        except Exception as exc:
            return CompletedHandle(error=exc)

    def execute(self, selected, values):
        return self.submit(selected, values).result()

    def _run(self, selected, values):
        torch = _torch()
        model = get_model(selected.model_id)
        precision = selected.candidate.precision
        expected = artifact_id(selected.model_id,
                               source_digest(selected.model_id),
                               precision, transform_version(precision),
                               {"backend": self._profile.name})
        if (selected.artifact_id != expected
                or selected.candidate.backend != self._profile.name):
            raise Rejection("INVALID_PLAN", "Artifact or backend mismatch")
        if precision not in self._profile.precisions:
            raise Rejection("INVALID_PLAN", "Unsupported precision")
        dtype = torch.float64 if precision == "fp64" else torch.float32
        device = torch.device("cuda", 0)
        with torch.no_grad():
            inputs = torch.tensor(list(values), dtype=dtype, device=device)
            if model.get("kind") == "multinomial-logreg":
                weights = torch.tensor(model["weights"], dtype=dtype,
                                       device=device)
                bias = torch.tensor(model["bias"], dtype=dtype,
                                    device=device)
                scores = (weights @ inputs + bias).tolist()
                label = max(range(len(scores)), key=lambda c: scores[c])
                return {"scores": scores, "label": label,
                        "label_name": model["classes"][label]}
            weights = torch.tensor(model["weights"], dtype=dtype,
                                   device=device)
            score = (torch.dot(weights, inputs) + float(model["bias"])).item()
        return {"score": score, "label": int(score >= 0)}


if __name__ == "__main__":
    # The discovery probe's child process: `python -m aacl.backends.gpu`
    # probes the device and prints the result as one line of JSON.
    _probe_child_main()
