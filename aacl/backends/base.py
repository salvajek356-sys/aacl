"""The backend contract. Phase 0 shape, as in the v0.1 proof: synchronous
capabilities() + execute(). The async handle contract (companion §5) replaces
execute()'s shape in Phase 1 — deliberately, as its own phase, not smuggled in."""
from typing import Protocol


class Backend(Protocol):
    def capabilities(self): ...
    def execute(self, plan, values): ...
