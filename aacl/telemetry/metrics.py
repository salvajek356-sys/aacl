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

Phase 3: an event that reached execution also carries `attempts` — one
record per attempt, in order, each naming its candidate, its artifact, its
outcome, its failure class when it has one, and its timing — and a
`fallback` flag, true when any attempt before the outcome did not produce
it. The event's `artifact_id` / `backend` / `precision` name the plan's
chosen candidate; the attempts name what actually ran.

Phase 4: when the workload named a quality reference, the event also
carries `quality_reference` and `quality_drift` — the chosen artifact's
measured drift against that reference, recorded per run next to the
timings it belongs with.
"""


def new_event(request_id):
    return {"request_id": request_id, "success": False, "fallback": False}
