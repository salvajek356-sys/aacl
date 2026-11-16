"""Scoring. Phase 0 keeps the v0.1 proof's selector — a static precision
preference — and keeps its honest name: this is NOT a latency estimate.
Target-pressure scoring (companion §1) replaces this module's internals in
Phase 2; the planner's call shape does not change."""


def select(candidates):
    """The winning candidate under the static precision preference."""
    return min(candidates, key=lambda c: (c.preference_rank, c.backend, c.precision))


REASON = "STATIC_PRECISION_PREFERENCE_NOT_LATENCY_ESTIMATE"
