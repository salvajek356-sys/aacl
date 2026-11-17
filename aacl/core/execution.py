"""Execution candidates and plans. A plan names its chosen candidate and,
since Phase 3 (companion §2), carries the ranked list of every survivor
behind it: the executor's fallback order, in the plan, not improvised at
failure time.

Phase 1: the plan carries its own explanation — a human-readable sentence
derived from the actual selection, the artifact identity, and the workload's
declared targets — so every response can say why this plan, in words.

Phase 2: the plan also carries the chosen candidate's static estimates, in
fields named `estimated_*` so no reader can mistake them for measurements.

Phase 3: `ranked` holds the scorer's ScoredCandidate for every survivor,
best first (ranked[0] is the chosen candidate). The entries carry their
estimates, pressures, and reliability flags, so the fallback order the
executor will follow is inspectable before anything runs.

Phase 4: the plan names its model (`model_id` — the executor's attempts
and the backend need it now that there are two) and, when the workload
declared a quality reference, carries the chosen candidate's *measured*
drift (`quality_drift`) — the one set of figures on the plan that is a
measurement rather than an estimate.
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
    estimated_latency_ms: float = None
    estimated_memory_mb: float = None
    estimated_cost: float = None
    ranked: tuple = ()
    # Set explicitly by the planner on every plan it builds; the default
    # exists only for hand-built plans in tests and tools, which have
    # always meant the demo model.
    model_id: str = "linear-demo-v1"
    quality_drift: dict = None
