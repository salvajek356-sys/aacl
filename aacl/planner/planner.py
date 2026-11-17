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
"""
import hashlib
import json
from dataclasses import asdict

from ..core.execution import ExecutionPlan
from ..core.workload import Rejection
from ..policy.engine import admissible
from . import candidate_generator, explain, scorer


def plan(spec, profile):
    candidates = candidate_generator.generate(profile)
    valid = [c for c in admissible(spec, candidates) if c.precision in spec.allowed_precisions]
    if not valid:
        raise Rejection("NO_VALID_PLAN", "No permitted, supported execution path")
    selection = scorer.select(spec, profile, valid)
    chosen = selection.chosen.candidate
    artifact = selection.chosen.artifact
    identity = json.dumps({"artifact": artifact, "candidate": asdict(chosen)}, sort_keys=True)
    est = selection.chosen.estimate
    return ExecutionPlan(hashlib.sha256(identity.encode()).hexdigest()[:16], chosen, artifact,
                         selection.reason, explain.explain(spec, selection, artifact),
                         est.estimated_latency_ms, est.estimated_memory_mb,
                         est.estimated_cost), candidates
