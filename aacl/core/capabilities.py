"""BackendProfile: what a backend can do, discovered from the machine it
woke up on.

Phase 0 carried static defaults, as in the v0.1 proof. Phase 2 replaces them
with real discovery (roadmap M2): core count, physical and available memory,
and a cache ceiling are read from the operating system when this module is
imported — once, so every profile built in a process describes the same
machine and planning stays deterministic within a run.

The precision list is not discovered from the hardware; it is the set the
CPU backend actually implements — fp64 natively, fp32 by explicit rounding
at every step. int8 is parseable in a request but no backend offers it, so
it is honestly absent here. A future backend declares its own list the same
way: what it can really run, nothing more.

`max_cache_bytes` is derived from *total* memory — a quarter of it — not
from available memory: available memory fluctuates second to second, and a
cache ceiling that moved between two identical requests would make plans
non-deterministic. Available memory is recorded as the fact it was at
discovery time; nothing in planning spends it yet (the artifact cache that
will consult `max_cache_bytes` is Phase 3).
"""
import os
import platform
from dataclasses import dataclass


def _logical_cores():
    """Cores usable by this process, not just present in the machine."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def _total_memory_bytes():
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        return None


def _available_memory_bytes():
    """MemAvailable from /proc/meminfo on Linux; total memory elsewhere."""
    try:
        with open("/proc/meminfo", encoding="ascii") as meminfo:
            for line in meminfo:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return _total_memory_bytes()


# Discovered once, at import: the machine this process woke up on.
_CORES = _logical_cores()
_TOTAL_MEMORY_BYTES = _total_memory_bytes()
_AVAILABLE_MEMORY_BYTES = _available_memory_bytes()
_MAX_CACHE_BYTES = _TOTAL_MEMORY_BYTES // 4 if _TOTAL_MEMORY_BYTES else None


@dataclass(frozen=True)
class BackendProfile:
    name: str = "cpu-python"
    architecture: str = platform.machine()
    logical_cores: int = _CORES
    runtime: str = platform.python_version()
    precisions: tuple = ("fp32", "fp64")
    local: bool = True
    total_memory_bytes: int = _TOTAL_MEMORY_BYTES
    available_memory_bytes: int = _AVAILABLE_MEMORY_BYTES
    max_cache_bytes: int = _MAX_CACHE_BYTES
