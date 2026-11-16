"""BackendProfile: what a backend can do. Static defaults in Phase 0, as in
the v0.1 proof; real discovery arrives in Phase 2."""
import os
import platform
from dataclasses import dataclass


@dataclass(frozen=True)
class BackendProfile:
    name: str = "cpu-python"
    architecture: str = platform.machine()
    logical_cores: int = os.cpu_count() or 1
    runtime: str = platform.python_version()
    precisions: tuple = ("fp32", "fp64")
    local: bool = True
