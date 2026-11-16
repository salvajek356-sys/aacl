"""Telemetry recording: one JSONL event per request, appended, inputs never
recorded. Phase 0 writes exactly the v0.1 proof's event shape; the load/init
split and per-attempt records arrive in Phases 1 and 3."""
import json


class TelemetryRecorder:
    def __init__(self, path):
        self.path = path

    def record(self, event):
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
