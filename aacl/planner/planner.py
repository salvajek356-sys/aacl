"""The planner: generate candidates, filter by hard constraints and policy,
then select. Same order of operations — and the same plan identity — as the
v0.1 proof."""
import hashlib
import json
from dataclasses import asdict

from ..core.workload import Rejection
from ..models.registry import ARTIFACT_ID
from ..policy.engine import admissible
from . import candidate_generator, scorer


def plan(spec, profile):
    candidates = candidate_generator.generate(profile)
    valid = [c for c in admissible(spec, candidates) if c.precision in spec.allowed_precisions]
    if not valid:
        raise Rejection("NO_VALID_PLAN", "No permitted, supported execution path")
    chosen = scorer.select(valid)
    identity = json.dumps({"model": ARTIFACT_ID, "candidate": asdict(chosen)}, sort_keys=True)
    from ..core.execution import ExecutionPlan

    return ExecutionPlan(hashlib.sha256(identity.encode()).hexdigest()[:16], chosen, ARTIFACT_ID,
                         scorer.REASON), candidates
