"""Plan explanations: the human-readable account of a selection, derived from
the actual plan — chosen candidate, artifact identity, the selector's reason,
and the workload's declared targets. Built only from deterministic inputs,
so the same request always produces the same sentence.

Phase 1 honesty rule: the explanation names what the declared targets are
doing here — carried and recorded, not yet scored. Target-pressure scoring
(Phase 2) is what will make targets steer the choice; quality measurement
against a declared reference is Phase 4. The sentence says so rather than
letting a declared target look honored when it was only noted.
"""
from . import scorer


def _fmt(value):
    return repr(float(value))


def explain(spec, chosen, artifact):
    parts = [
        f"Selected {chosen.backend}/{chosen.precision} for {spec.model_id} "
        f"(artifact {artifact[:12]}…): {scorer.REASON} — selection is a static "
        f"precision preference, explicitly not a latency estimate."
    ]
    targets = []
    if spec.latency_target_ms is not None:
        targets.append(f"latency_target_ms={_fmt(spec.latency_target_ms)}")
    if spec.memory_limit_mb is not None:
        targets.append(f"memory_limit_mb={_fmt(spec.memory_limit_mb)}")
    if spec.cost_budget is not None:
        targets.append(f"cost_budget={_fmt(spec.cost_budget)}")
    declared = ", ".join(targets) if targets else "no latency/memory/cost targets"
    parts.append(
        f"Workload declares {declared}; optimize_for={spec.optimize_for}. "
        f"Phase 1 carries these into the plan without scoring against them — "
        f"target-pressure scoring arrives in Phase 2."
    )
    if spec.quality_reference is not None:
        parts.append(
            f"Quality reference '{spec.quality_reference}' declared; drift "
            f"against it is not measured until Phase 4."
        )
    else:
        parts.append("No quality reference declared — quality unmeasured.")
    return " ".join(parts)
