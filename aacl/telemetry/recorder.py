"""Telemetry recording: one JSONL event per request, appended, inputs never
recorded. Phase 1 events carry the load/init timing split (see metrics.py);
Phase 3 events that reach execution carry a record per attempt inside the
request's event — one line per request still, attempts and all."""
import json


class TelemetryRecorder:
    def __init__(self, path):
        self.path = path

    def record(self, event):
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
