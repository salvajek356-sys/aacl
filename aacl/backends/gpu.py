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
from ..core.capabilities import BackendProfile
from ..core.workload import Rejection
from ..models.registry import (artifact_id, get_model, source_digest,
                               transform_version)
from .base import CompletedHandle

_PROFILE_UNSET = object()
_profile_cache = _PROFILE_UNSET


def _torch():
    """The one place torch is imported. Lazy and optional by design."""
    import torch
    return torch


def probe_gpu_profile():
    """The GPU's BackendProfile, discovered by probing the device — or
    None, when there is honestly no GPU to describe: torch absent, no
    device answering, or no precision genuinely executing on it.

    Cached after the first probe: discovery is a single deterministic
    snapshot per process, as with the CPU profile.
    """
    global _profile_cache
    if _profile_cache is not _PROFILE_UNSET:
        return _profile_cache
    _profile_cache = _probe()
    return _profile_cache


def _probe():
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
        return BackendProfile(
            name="gpu-rocm" if hip else "gpu-cuda",
            architecture=str(props.name),
            logical_cores=int(props.multi_processor_count),
            runtime=str(torch.__version__),
            precisions=tuple(precisions),
            local=True,
            total_memory_bytes=total,
            available_memory_bytes=total - int(torch.cuda.memory_allocated(0)),
            max_cache_bytes=total // 4,
        )
    except Exception:
        return None


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
