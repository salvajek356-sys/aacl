"""AACL — Agentic Acceleration Compatibility Layer.

Phase 0: the v0.1 architecture proof, ported into the roadmap's package
layout with behavior unchanged. The public surface re-exported here is the
proof's, so its tests and proof script run unmodified.
"""
from .api.service import Runtime, make_server
from .backends.cpu import CPUBackend
from .core.capabilities import BackendProfile
from .core.execution import ExecutionCandidate, ExecutionPlan
from .core.workload import Rejection, WorkloadSpec
from .planner.planner import plan
from .policy.rules import policy_allows

__all__ = [
    "Runtime",
    "make_server",
    "CPUBackend",
    "BackendProfile",
    "ExecutionCandidate",
    "ExecutionPlan",
    "Rejection",
    "WorkloadSpec",
    "plan",
    "policy_allows",
]
