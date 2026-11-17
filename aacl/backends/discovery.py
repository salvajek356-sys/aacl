"""Backend discovery and registration (Phase 5): the set of backends
that genuinely exist on this machine, discovered once and held as the
process's snapshot.

The CPU reference backend is always registered, and first: it is the
primary — the profile a plan is anchored to, and the default home of
the standing precision preference. The GPU backend is registered only
when its own probe (backends/gpu.py) finds torch importable and a
device genuinely answering; absent either, the registry is the CPU
alone and every behavior in the runtime is Phase 4's, byte for byte.

This module is the registration seam the leak test allows: the one
place that knows which backends exist. Candidate generation consults
it for the search space, the composition root (api/service.py) builds
the runtime's dispatching backend from it, and nothing above those
seams changes when a backend arrives or doesn't.
"""
from .cpu import CPUBackend
from .gpu import GPUBackend

_SNAPSHOT = None


def _build():
    backends = {}
    cpu = CPUBackend()
    backends[cpu.capabilities().name] = cpu
    gpu = GPUBackend.discover()
    if gpu is not None:
        backends[gpu.capabilities().name] = gpu
    return backends


def registered_backends():
    """name → backend instance, in registration order (CPU first).
    Built once per process: the machine does not change its mind
    mid-run, and planning stays deterministic because of it."""
    global _SNAPSHOT
    if _SNAPSHOT is None:
        _SNAPSHOT = _build()
    return _SNAPSHOT


def registered_profiles():
    """The discovered profile of every registered backend."""
    return tuple(b.capabilities() for b in registered_backends().values())


def primary_profile():
    """The primary backend's profile — the CPU reference backend's,
    since it is registered first and always."""
    return next(iter(registered_backends().values())).capabilities()


def build_router():
    """The runtime's default backend: every registered backend behind
    one dispatching front (backends/router.py)."""
    from .router import BackendRouter
    backends = registered_backends()
    return BackendRouter(backends, primary=next(iter(backends)))
