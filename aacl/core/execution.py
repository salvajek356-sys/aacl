"""Execution candidates and plans. Phase 0 shape, as in the v0.1 proof: a plan
names a single chosen candidate. The ranked-fallback plan shape arrives in
Phase 3 (companion §2)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCandidate:
    backend: str
    precision: str
    local: bool
    preference_rank: int


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    candidate: ExecutionCandidate
    artifact_id: str
    reason: str
