"""AACL — Agentic Acceleration Compatibility Layer.

Phase 0: the v0.1 architecture proof, ported into the roadmap's package
layout with behavior unchanged. Phase 1: contracts v2 — WorkloadSpec targets
with validation, the async backend handle contract, generalized artifact
identity, the load/init telemetry split, plan explanations, and unsigned
receipt stubs. Phase 2: planning for real — CPU capability discovery,
static candidate estimates, and target-pressure scoring with explanations.
Phase 3: fallback as a protocol — ranked plans, an executor that re-gates
policy per attempt and classifies every failure, a reliability registry
that downgrades capability lies, and a bounded, pinning artifact cache.
Phase 4: quantization and measured quality — a genuinely trained model,
a transformation service that calibrates and produces a real int8
artifact the CPU backend executes, and drift measured against a named
reference, scored when the workload declares a tolerance for it.
Phase 5: a second backend — the GPU, behind the same contracts, with
discovery that probes the device and registers nothing when there is
honestly nothing to register. The leak test (a mechanical diff audit
against the Phase 4 commit) and the GPU run itself belong to a session
on hardware this package's build machine does not have; the backend is
built, the verdict is pending.
The public surface re-exported here keeps the proof's names, so its tests
and proof script run against the package.
"""
from .api.service import Runtime, make_server
from .backends.base import CompletedHandle
from .backends.cpu import CPUBackend
from .backends.gpu import GPUBackend
from .core.capabilities import BackendProfile
from .core.execution import ExecutionCandidate, ExecutionPlan
from .core.executor import Executor
from .core.failures import (AttemptRecord, CapabilityLie, ExecutionFailed,
                           FailureClass)
from .core.workload import Rejection, WorkloadSpec
from .models.cache import ArtifactCache
from .models.registry import ReliabilityRegistry, artifact_id
from .planner.planner import plan
from .policy.rules import policy_allows

__all__ = [
    "Runtime",
    "make_server",
    "CPUBackend",
    "GPUBackend",
    "CompletedHandle",
    "BackendProfile",
    "ExecutionCandidate",
    "ExecutionPlan",
    "Executor",
    "AttemptRecord",
    "CapabilityLie",
    "ExecutionFailed",
    "FailureClass",
    "Rejection",
    "WorkloadSpec",
    "ArtifactCache",
    "ReliabilityRegistry",
    "artifact_id",
    "plan",
    "policy_allows",
]
