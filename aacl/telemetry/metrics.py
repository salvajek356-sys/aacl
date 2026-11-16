"""Execution metrics: the event skeleton every request starts from.
Field set is the v0.1 proof's; richer metrics land with their phases."""


def new_event(request_id):
    return {"request_id": request_id, "success": False, "fallback": False}
