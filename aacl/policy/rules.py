"""Policy rules. Policy is an independent, deterministic gate — separate from
feasibility — exactly as the roadmap §11 requires. Phase 0 carries the proof's
single rule: local-only workloads may not run on non-local candidates."""


def policy_allows(spec, candidate):
    return not (spec.local_only and not candidate.local)
