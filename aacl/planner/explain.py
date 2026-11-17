"""Plan explanations: the human-readable account of a selection, derived from
the actual plan — chosen candidate, artifact identity, the pressures that
decided it, and the workload's declared targets. Built only from
deterministic inputs, so the same request always produces the same sentence.

Phase 2 honesty rules, succeeding Phase 1's "recorded, not scored":

- Declared targets are now scored against, and the sentence shows the
  arithmetic: the chosen candidate's binding pressure as a percentage of
  its budget, computed from its static estimate. Estimates are named as
  estimates in the sentence itself — never dressed as measurements.
- Quality is still not measured (that is Phase 4). A declared reference is
  named, and the sentence states plainly that quality contributed no
  pressure and no score.
- With no budgets declared there is no pressure to report, and the
  sentence says selection followed the standing precision preference
  instead of inventing a pressure figure.
"""
from . import scorer

_BUDGET_NOUN = {"latency": "latency budget", "memory": "memory budget",
                "cost": "cost budget"}
_BUDGET_VALUE = {"latency": "latency_target_ms", "memory": "memory_limit_mb",
                 "cost": "cost_budget"}
_ESTIMATE_VALUE = {"latency": "estimated_latency_ms", "memory": "estimated_memory_mb",
                   "cost": "estimated_cost"}
_ESTIMATE_NOUN = {"latency": "estimated latency", "memory": "estimated memory",
                  "cost": "estimated cost"}
_UNITS = {"latency": "ms", "memory": "MB", "cost": "cost units"}


def _fmt(value):
    return repr(float(value))


def _pct(pressure):
    pct = pressure * 100
    return f"{pct:.0f}%" if pct >= 1 else f"{pct:.2f}%"


def _selection_sentence(spec, selection, artifact):
    chosen = selection.chosen
    head = (f"Selected {chosen.candidate.backend}/{chosen.candidate.precision} "
            f"for {spec.model_id} (artifact {artifact[:12]}…): ")
    if selection.reason == scorer.NO_TARGET_REASON:
        return head + (
            "no latency, memory, or cost targets declared, so there is no "
            "target pressure to score; selection follows the standing "
            "precision preference — a preference, not a measurement."
        )
    dim = chosen.binding_dimension
    estimate = getattr(chosen.estimate, _ESTIMATE_VALUE[dim])
    budget = getattr(spec, _BUDGET_VALUE[dim])
    parts = [head + (
        f"target-pressure minimax — its binding constraint is {dim}, where "
        f"its {_ESTIMATE_NOUN[dim]} of {_fmt(estimate)} {_UNITS[dim]} sits at "
        f"{_pct(chosen.worst_pressure)} of its {_BUDGET_NOUN[dim]} "
        f"({_fmt(budget)} {_UNITS[dim]})."
    )]
    others = [s for s in selection.scored if s is not chosen]
    if others:
        runner = min(others, key=lambda s: s.worst_pressure)
        parts.append(
            f"The next candidate ({runner.candidate.backend}/"
            f"{runner.candidate.precision}) reaches "
            f"{_pct(runner.worst_pressure)} of its "
            f"{_BUDGET_NOUN[runner.binding_dimension]}."
        )
    parts.append("All candidate figures are static capability estimates, not measurements.")
    return " ".join(parts)


def explain(spec, selection, artifact):
    parts = [_selection_sentence(spec, selection, artifact)]
    targets = []
    if spec.latency_target_ms is not None:
        targets.append(f"latency_target_ms={_fmt(spec.latency_target_ms)}")
    if spec.memory_limit_mb is not None:
        targets.append(f"memory_limit_mb={_fmt(spec.memory_limit_mb)}")
    if spec.cost_budget is not None:
        targets.append(f"cost_budget={_fmt(spec.cost_budget)}")
    declared = ", ".join(targets) if targets else "no latency/memory/cost targets"
    parts.append(f"Workload declares {declared}; optimize_for={spec.optimize_for}.")
    if spec.quality_reference is not None:
        parts.append(
            f"Quality reference '{spec.quality_reference}' declared; quality "
            f"is unmeasured in Phase 2 — it contributes no pressure and no "
            f"score. Measurement against the reference arrives in Phase 4."
        )
    else:
        parts.append("No quality reference declared — quality unmeasured.")
    return " ".join(parts)
