"""The executor (Phase 3, companion §2): a plan's ranked alternatives, tried
in order, each re-gated by policy, with a named failure class for every
attempt and a typed error when all of them fail.

The rules, stated plainly:

- Attempts follow the plan's ranked order. The bound is the ranked list
  itself, capped at MAX_ATTEMPTS, so a many-backend future cannot loop.
- Policy is re-checked per attempt, against the live gate — not assumed
  from plan time. A candidate the gate denies is recorded as a
  POLICY_DENIAL attempt and never executed.
- A failure is classified, never swallowed (see core/failures.py). A
  capability lie also downgrades the registry entry for that backend,
  model, and precision, so the next plan deprioritizes it.
- The first success ends the run. The outcome names what ran, what was
  tried before it, and whether any fallback happened.
"""
import time
from dataclasses import dataclass, replace

from .failures import AttemptRecord, ExecutionFailed, FailureClass, classify
from ..models.registry import ReliabilityRegistry
from ..policy.rules import policy_allows

MAX_ATTEMPTS = 8


@dataclass(frozen=True)
class ExecutionOutcome:
    output: object
    attempts: tuple  # AttemptRecord, in the order tried
    executed: tuple  # (candidate, artifact_id) that produced the output
    fallback: bool    # True when any attempt before the success did not run it


class Executor:
    def __init__(self, backend, reliability=None, policy_gate=None):
        self.backend = backend
        self.reliability = (reliability if reliability is not None
                            else ReliabilityRegistry())
        self.policy_gate = policy_gate if policy_gate is not None else policy_allows

    def execute(self, selected, spec, values):
        attempts = []
        for candidate, artifact in self._attempts_for(selected)[:MAX_ATTEMPTS]:
            start = time.perf_counter_ns()
            if not self.policy_gate(spec, candidate):
                attempts.append(AttemptRecord(
                    candidate.backend, candidate.precision, artifact, "denied",
                    FailureClass.POLICY_DENIAL,
                    "policy denied this candidate at execution",
                    self._ms(start)))
                continue
            attempt_plan = replace(selected, candidate=candidate,
                                   artifact_id=artifact)
            handle = self.backend.submit(attempt_plan, values)
            try:
                output = handle.result()
            except Exception as exc:
                failure_class = classify(exc)
                if failure_class == FailureClass.CAPABILITY_LIE:
                    self.reliability.record_lie(candidate.backend,
                                                spec.model_id,
                                                candidate.precision)
                attempts.append(AttemptRecord(
                    candidate.backend, candidate.precision, artifact, "failed",
                    failure_class, str(exc), self._ms(start)))
                continue
            attempts.append(AttemptRecord(
                candidate.backend, candidate.precision, artifact, "succeeded",
                None, "", self._ms(start)))
            return ExecutionOutcome(
                output, tuple(attempts), (candidate, artifact),
                any(a.outcome != "succeeded" for a in attempts))
        raise ExecutionFailed(attempts)

    @staticmethod
    def _attempts_for(selected):
        """The (candidate, artifact_id) pairs to try, in ranked order.

        A plan built before Phase 3 carries no ranked list; it is tried as
        the single candidate it names.
        """
        if selected.ranked:
            return [(s.candidate, s.artifact) for s in selected.ranked]
        return [(selected.candidate, selected.artifact_id)]

    @staticmethod
    def _ms(start):
        return (time.perf_counter_ns() - start) / 1e6
