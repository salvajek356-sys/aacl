"""Failure classes and the typed total-failure error (Phase 3, companion §2).

A failure is a fact with a name, not a stack trace to be swallowed. Four
classes, and only four:

- CAPABILITY_LIE — a backend rejected an operation it claimed to support.
  The claim is the lie; the rejection is the evidence. This one also
  downgrades the registry entry for that backend, model, and precision, so
  the next plan deprioritizes it.
- BACKEND_ERROR — anything else a backend raised while executing.
- POLICY_DENIAL — the policy gate refused a candidate at execution time.
  The candidate was never run; the denial is the record.
- TIMEOUT — a backend that raised a timeout. The class exists so the
  executor can name one honestly if a backend ever produces it; no timeout
  is fabricated in this phase.
"""
from dataclasses import dataclass

from .workload import Rejection


class FailureClass:
    CAPABILITY_LIE = "CAPABILITY_LIE"
    BACKEND_ERROR = "BACKEND_ERROR"
    POLICY_DENIAL = "POLICY_DENIAL"
    TIMEOUT = "TIMEOUT"


class CapabilityLie(Rejection):
    """A backend rejected an operation it claimed to support.

    Raised by the backend itself, which is the only party that knows it
    claimed the operation and then refused it. The executor trusts the
    report, records the lie, and moves on.
    """

    def __init__(self, message):
        super().__init__("CAPABILITY_LIE", message)


def classify(exc):
    """The failure class of an exception raised by a backend at execution.

    A CapabilityLie — or any typed refusal carrying the CAPABILITY_LIE code
    — is a lie. A TimeoutError is a timeout. Everything else a backend
    raises is a backend error. Nothing is classified by reading a message.
    """
    if isinstance(exc, CapabilityLie):
        return FailureClass.CAPABILITY_LIE
    if isinstance(exc, Rejection) and exc.code == "CAPABILITY_LIE":
        return FailureClass.CAPABILITY_LIE
    if isinstance(exc, TimeoutError):
        return FailureClass.TIMEOUT
    return FailureClass.BACKEND_ERROR


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt at one candidate: what was tried, what happened, how long.

    `outcome` is "succeeded", "failed", or "denied" (policy refused the
    candidate before it could run). `failure_class` is None on success and
    one of FailureClass's names otherwise. `detail` carries the backend's
    own words, verbatim — it is evidence, not a diagnosis.
    """

    backend: str
    precision: str
    artifact_id: str
    outcome: str
    failure_class: str = None
    detail: str = ""
    attempt_ms: float = 0.0


class ExecutionFailed(Rejection):
    """Every attempt failed. The error names every attempt and its class.

    The attempts are carried on the exception itself, so the runtime can
    record them in telemetry even as the failure propagates.
    """

    def __init__(self, attempts):
        self.attempts = tuple(attempts)
        summary = "; ".join(
            f"{a.backend}/{a.precision} {a.failure_class}"
            + (f": {a.detail}" if a.detail else "")
            for a in self.attempts
        )
        super().__init__(
            "EXECUTION_FAILED",
            f"All {len(self.attempts)} attempts failed: {summary}",
        )
