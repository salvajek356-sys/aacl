"""AACL — Agentic Acceleration Compatibility Layer.

Phase 0: the v0.1 architecture proof, ported into the roadmap's package
layout with behavior unchanged. Phase 1: contracts v2 — WorkloadSpec targets
with validation, the async backend handle contract, generalized artifact
identity, the load/init telemetry split, plan explanations, and unsigned
receipt stubs. The public surface re-exported here keeps the proof's names,
so its tests and proof script run against the package.
"""
from .api.service import Runtime, make_server
from .backends.base import CompletedHandle
from .backends.cpu import CPUBackend
from .core.capabilities import BackendProfile
from .core.execution import ExecutionCandidate, ExecutionPlan
from .core.workload import Rejection, WorkloadSpec
from .models.registry import artifact_id
from .planner.planner import plan
from .policy.rules import policy_allows

__all__ = [
    "Runtime",
    "make_server",
    "CPUBackend",
    "CompletedHandle",
    "BackendProfile",
    "ExecutionCandidate",
    "ExecutionPlan",
    "Rejection",
    "WorkloadSpec",
    "artifact_id",
    "plan",
    "policy_allows",
]
