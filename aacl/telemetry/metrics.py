"""Execution metrics: the event skeleton every request starts from.

Phase 1 splits the request's setup time into two recorded fields:

- `init_ms` — backend initialization for the request: fetching the backend's
  capability profile, the machine introducing itself.
- `load_ms` — workload load: validating the spec, planning, and resolving
  the artifact identity — everything needed to know *what* would run.

`inference_ms` (set by the runtime) remains the execution itself, and
`runtime_ms_excluding_telemetry_write` the whole request. Fields are set as
their phase completes; a request refused during load has an `init_ms` and no
`load_ms`, which is itself information.
"""


def new_event(request_id):
    return {"request_id": request_id, "success": False, "fallback": False}
