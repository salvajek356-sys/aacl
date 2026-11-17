"""The backend contract (Phase 1, companion §5): asynchronous in shape from
the start, so a slow or remote backend later changes nothing above this line.

A backend exposes `capabilities()` and `submit(plan, values)`, which returns
an ExecutionHandle immediately. The handle exposes:

- `result()` — the execution output, or the execution's error, raised.
- `cancel()` — request cancellation; returns True only if work was actually
  stopped. Accepting the request and having nothing to stop is honest, and
  reported as False.
- `stream()` — OPTIONAL. A handle that can stream yields output chunks; one
  that cannot may omit it. Callers must not assume it exists.

CompletedHandle is the trivial handle for backends that finish synchronously:
already completed at submit time, `stream()` yields its single result as one
chunk, and `cancel()` accepts the call, stops nothing, and says so.
"""
from typing import Protocol


class ExecutionHandle(Protocol):
    def result(self): ...
    def cancel(self): ...
    # stream() is optional and intentionally not part of the protocol.


class Backend(Protocol):
    def capabilities(self): ...
    def submit(self, plan, values): ...


class CompletedHandle:
    """An already-finished execution, for synchronous backends."""

    def __init__(self, output=None, error=None):
        self._output = output
        self._error = error

    def result(self):
        if self._error is not None:
            raise self._error
        return self._output

    def cancel(self):
        # The work finished before cancel could arrive: accept the call,
        # ignore it, and report that nothing was stopped.
        return False

    def stream(self):
        yield self.result()
