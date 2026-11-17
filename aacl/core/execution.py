"""Execution candidates and plans. A plan names a single chosen candidate;
the ranked-fallback plan shape arrives in Phase 3 (companion §2).

Phase 1: the plan carries its own explanation — a human-readable sentence
derived from the actual selection, the artifact identity, and the workload's
declared targets — so every response can say why this plan, in words.
"""
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
    explanation: str = ""
