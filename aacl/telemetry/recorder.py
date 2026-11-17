"""Telemetry recording: one JSONL event per request, appended, inputs never
recorded. Phase 1 events carry the load/init timing split (see metrics.py);
per-attempt records arrive in Phase 3."""
import json


class TelemetryRecorder:
    def __init__(self, path):
        self.path = path

    def record(self, event):
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
