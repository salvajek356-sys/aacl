"""The policy engine: applies the rules to a candidate list. Kept separate from
the planner so the gate can grow (quotas, arbitration) without the planner
changing shape — arbitration itself is Phase 7."""
from .rules import policy_allows


def admissible(spec, candidates):
    """The candidates policy permits, in their original order."""
    return [c for c in candidates if policy_allows(spec, c)]
