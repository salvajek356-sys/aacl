"""Candidate generation: the feasible search space, before any filtering or
scoring. Phase 0 generates the proof's two CPU precision paths."""


def generate(profile):
    from ..core.execution import ExecutionCandidate

    return [ExecutionCandidate(profile.name, p, profile.local, rank)
            for rank, p in enumerate(("fp64", "fp32")) if p in profile.precisions]
