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

Phase 3: when a scored candidate stands downgraded — its backend was
caught in a capability lie — the sentence names it and says it was
deprioritized. When the downgraded candidate is the one selected, the
sentence says it runs as a last resort. A downgrade is never left to be
inferred from a changed choice.

Phase 4: quality is measured, and the sentences keep the two kinds of
figure visibly apart. Latency, memory, and cost are still static
estimates and are named as estimates. Drift is a measurement — taken
against the named reference's eval rows — and is reported as one: the
selected artifact's mean and max score error and its label
disagreements, plus its quality pressure when a tolerance was declared.
With no reference declared there is nothing to measure against, and the
sentence says exactly that: "quality unmeasured — no reference."
"""
from . import scorer

_BUDGET_NOUN = {"latency": "latency budget", "memory": "memory budget",
                "cost": "cost budget", "quality": "quality drift budget"}
_BUDGET_VALUE = {"latency": "latency_target_ms", "memory": "memory_limit_mb",
                 "cost": "cost_budget"}
_ESTIMATE_VALUE = {"latency": "estimated_latency_ms", "memory": "estimated_memory_mb",
                   "cost": "estimated_cost"}
_ESTIMATE_NOUN = {"latency": "estimated latency", "memory": "estimated memory",
                  "cost": "estimated cost"}
_UNITS = {"latency": "ms", "memory": "MB", "cost": "cost units", "quality": ""}


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
    if dim == "quality":
        binding = (
            f"target-pressure minimax — its binding constraint is quality, "
            f"where its measured mean score error of "
            f"{_fmt(chosen.drift['mean_score_error'])} sits at "
            f"{_pct(chosen.worst_pressure)} of its quality drift budget "
            f"(quality_max_drift={_fmt(spec.quality_max_drift)})."
        )
    else:
        estimate = getattr(chosen.estimate, _ESTIMATE_VALUE[dim])
        budget = getattr(spec, _BUDGET_VALUE[dim])
        binding = (
            f"target-pressure minimax — its binding constraint is {dim}, where "
            f"its {_ESTIMATE_NOUN[dim]} of {_fmt(estimate)} {_UNITS[dim]} sits at "
            f"{_pct(chosen.worst_pressure)} of its {_BUDGET_NOUN[dim]} "
            f"({_fmt(budget)} {_UNITS[dim]})."
        )
    parts = [head + binding]
    others = [s for s in selection.scored if s is not chosen]
    if others:
        runner = min(others, key=lambda s: s.worst_pressure)
        parts.append(
            f"The next candidate ({runner.candidate.backend}/"
            f"{runner.candidate.precision}) reaches "
            f"{_pct(runner.worst_pressure)} of its "
            f"{_BUDGET_NOUN[runner.binding_dimension]}."
        )
    parts.append("Latency, memory, and cost figures are static capability "
                 "estimates, not measurements.")
    return " ".join(parts)


def explain(spec, selection, artifact):
    parts = [_selection_sentence(spec, selection, artifact)]
    downgraded = [s for s in selection.scored if s.downgraded]
    if downgraded:
        names = ", ".join(f"{s.candidate.backend}/{s.candidate.precision}"
                          for s in downgraded)
        if selection.chosen.downgraded:
            parts.append(
                f"Reliability: {names} stands downgraded — a capability lie "
                f"was observed — and deprioritized; the selected candidate "
                f"is itself downgraded and runs as a last resort."
            )
        else:
            parts.append(
                f"Reliability: {names} stands downgraded — a capability lie "
                f"was observed — and is deprioritized below the alternatives."
            )
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
        drift = selection.chosen.drift
        parts.append(
            f"Quality reference '{spec.quality_reference}' declared — drift "
            f"measured against the model's floating-point artifact on its "
            f"{drift['eval_samples']} eval rows: the selected artifact's "
            f"mean score error is {_fmt(drift['mean_score_error'])}, max "
            f"{_fmt(drift['max_score_error'])}, with "
            f"{drift['label_disagreements']} label disagreements in "
            f"{drift['eval_samples']}."
        )
        if spec.quality_max_drift is not None:
            parts.append(
                f"quality_max_drift={_fmt(spec.quality_max_drift)} declared, "
                f"so measured quality pressure is scored in the minimax."
            )
        elif spec.optimize_for == "quality" and selection.chosen.pressures:
            parts.append(
                "No quality_max_drift declared, so quality contributes no "
                "pressure; ties in target pressure are ranked by the "
                "measured drift, as optimize_for=quality asks."
            )
        else:
            parts.append(
                "No quality_max_drift declared, so quality contributes no "
                "pressure."
            )
    else:
        parts.append("Quality contributes no pressure and no score: "
                     "quality unmeasured — no reference.")
    return " ".join(parts)
