"""The planner: generate candidates, filter by hard constraints and policy,
then select. Same order of operations as the v0.1 proof.

Phase 1: the chosen candidate's artifact identity is the generalized
content address — hash(model_id, source_digest, precision, transform_version,
backend_constraints) — the plan identity derives from it, and the plan
carries its explanation.

Phase 2: selection is target-pressure scoring over static capability
estimates (see scorer.py and estimates.py). The plan carries the chosen
candidate's estimates alongside its explanation, so a response shows both
the numbers scored and the sentence that accounts for them.

Phase 3: the plan also carries the scorer's ranked survivor list — the
executor's fallback order — and planning consults the reliability registry
when one is supplied, so a backend that lied about a capability is
deprioritized by the next plan. A caller with no registry gets every claim
trusted, exactly as before.

Phase 4: candidate generation is model-aware (the trained model gains an
int8 candidate), and the plan carries the chosen candidate's measured
quality drift when the workload named a reference — the plan's one
measurement among its estimates.
"""
import hashlib
import json
from dataclasses import asdict

from ..core.execution import ExecutionPlan
from ..core.workload import Rejection
from ..policy.engine import admissible
from . import candidate_generator, explain, scorer


def plan(spec, profile, reliability=None):
    candidates = candidate_generator.generate(profile, spec.model_id)
    valid = [c for c in admissible(spec, candidates) if c.precision in spec.allowed_precisions]
    if not valid:
        raise Rejection("NO_VALID_PLAN", "No permitted, supported execution path")
    selection = scorer.select(spec, profile, valid, reliability=reliability)
    chosen = selection.chosen.candidate
    artifact = selection.chosen.artifact
    identity = json.dumps({"artifact": artifact, "candidate": asdict(chosen)}, sort_keys=True)
    est = selection.chosen.estimate
    return ExecutionPlan(hashlib.sha256(identity.encode()).hexdigest()[:16], chosen, artifact,
                         selection.reason, explain.explain(spec, selection, artifact),
                         est.estimated_latency_ms, est.estimated_memory_mb,
                         est.estimated_cost, ranked=selection.ranked,
                         model_id=spec.model_id,
                         quality_drift=selection.chosen.drift), candidates
