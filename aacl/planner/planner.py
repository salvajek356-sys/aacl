"""The planner: generate candidates, filter by hard constraints and policy,
then select. Same order of operations as the v0.1 proof.

Phase 1: the chosen candidate's artifact identity is the generalized
content address — hash(model_id, source_digest, precision, transform_version,
backend_constraints) — the plan identity derives from it, and the plan
carries its explanation. Selection itself is unchanged: one candidate, by
the static precision preference. Scoring is Phase 2's work, not this phase's.
"""
import hashlib
import json
from dataclasses import asdict

from ..core.execution import ExecutionPlan
from ..core.workload import Rejection
from ..models.registry import SOURCE_DIGEST, TRANSFORM_VERSION, artifact_id
from ..policy.engine import admissible
from . import candidate_generator, explain, scorer


def plan(spec, profile):
    candidates = candidate_generator.generate(profile)
    valid = [c for c in admissible(spec, candidates) if c.precision in spec.allowed_precisions]
    if not valid:
        raise Rejection("NO_VALID_PLAN", "No permitted, supported execution path")
    chosen = scorer.select(valid)
    artifact = artifact_id(spec.model_id, SOURCE_DIGEST, chosen.precision,
                           TRANSFORM_VERSION, {"backend": chosen.backend})
    identity = json.dumps({"artifact": artifact, "candidate": asdict(chosen)}, sort_keys=True)
    return ExecutionPlan(hashlib.sha256(identity.encode()).hexdigest()[:16], chosen, artifact,
                         scorer.REASON, explain.explain(spec, chosen, artifact)), candidates
