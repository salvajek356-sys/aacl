"""The backend router (Phase 5): one front door for the registered
backends, and the execution half of the registration seam.

The router holds no policy and makes no choices. The planner — unchanged
— decides which candidate a plan names; the executor — unchanged —
walks the plan's ranked list and submits each attempt here; the router
delivers each attempt to the backend the candidate itself names, and
hands back that backend's handle untouched. Its capabilities() are the
primary backend's profile, because a plan is anchored to one profile
and the registry's primary is the CPU reference backend.

A candidate naming a backend the registry does not hold is refused in
writing, as an invalid plan — the same refusal a backend gives a plan
that isn't its own.
"""
from ..core.workload import Rejection
from .base import CompletedHandle


class BackendRouter:
    def __init__(self, backends, primary):
        if primary not in backends:
            raise ValueError(f"primary backend {primary!r} is not registered")
        self._backends = dict(backends)
        self._primary = primary

    def capabilities(self):
        return self._backends[self._primary].capabilities()

    def submit(self, selected, values):
        backend = self._backends.get(selected.candidate.backend)
        if backend is None:
            return CompletedHandle(error=Rejection(
                "INVALID_PLAN",
                f"No registered backend named {selected.candidate.backend!r}"))
        return backend.submit(selected, values)

    def execute(self, selected, values):
        return self.submit(selected, values).result()
