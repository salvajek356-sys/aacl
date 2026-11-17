"""The thin application-facing API (roadmap §12): POST /infer, kept boring on
purpose. Runtime flow, error codes, status codes, and body limits are the
v0.1 proof's, unchanged.

Phase 1: execution goes through the backend's async handle contract
(submit → result), the response gains the plan's explanation (inside the
plan) and an unsigned receipt stub, and telemetry records the load/init
timing split.

Phase 3: execution goes through the executor (core/executor.py) — the
plan's ranked alternatives, tried in order, each re-gated by policy, every
attempt recorded. The Runtime owns the reliability registry the planner
consults and the executor writes to, and an artifact cache bounded by the
backend profile's `max_cache_bytes`; a plan's artifacts are resolved into
the cache and pinned for the duration of the request. The response gains
`attempts` and `fallback`; the receipt names what actually ran. The
constructor accepts a backend so tests can inject a faulty one — the
fault-injection seam the fallback protocol is proved through.

Phase 4: a second model is served through the same flow, and when the
workload named a quality reference, the event records the chosen
artifact's measured drift (`quality_drift`, with `quality_reference`)
alongside the attempts — the run's one measurement, kept next to its
timings.

Phase 5: the default backend is no longer the CPU backend alone but the
registered set, composed by backends/discovery.py and dispatched by
backends/router.py — the CPU reference backend always, plus the GPU
backend when discovery genuinely finds a device. This file is the
composition root, so this is wiring, not flow: an explicitly injected
backend is still used exactly as given, and everything below this
constructor — planning, execution, telemetry, the response shape — is
unchanged.
"""
import argparse
import json
import time
import uuid
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..backends.discovery import build_router
from ..core.executor import Executor
from ..core.failures import ExecutionFailed
from ..core.workload import Rejection, WorkloadSpec
from ..models.cache import ArtifactCache
from ..models.registry import (ReliabilityRegistry, artifact_size_bytes,
                               transform_version)
from ..planner.planner import plan
from ..telemetry import metrics
from ..telemetry.receipt import build_receipt_stub
from ..telemetry.recorder import TelemetryRecorder


class Runtime:
    def __init__(self, telemetry_path="telemetry.jsonl", backend=None):
        self.backend = backend if backend is not None else build_router()
        self.telemetry_path = telemetry_path
        self.recorder = TelemetryRecorder(telemetry_path)
        self.reliability = ReliabilityRegistry()
        self.executor = Executor(self.backend, reliability=self.reliability)
        self.cache = None

    def infer(self, raw):
        start = time.perf_counter_ns()
        event = metrics.new_event(str(uuid.uuid4()))
        try:
            init_start = time.perf_counter_ns()
            profile = self.backend.capabilities()
            event["init_ms"] = (time.perf_counter_ns() - init_start) / 1e6
            load_start = time.perf_counter_ns()
            spec = WorkloadSpec.parse(raw)
            selected, candidates = plan(spec, profile, reliability=self.reliability)
            if self.cache is None:
                self.cache = ArtifactCache(profile.max_cache_bytes)
            pinned = self._resolve_artifacts(selected, spec)
            event["load_ms"] = (time.perf_counter_ns() - load_start) / 1e6
            execution_start = time.perf_counter_ns()
            try:
                outcome = self.executor.execute(selected, spec, spec.input)
            finally:
                for artifact in pinned:
                    self.cache.unpin(artifact)
            attempts = [asdict(a) for a in outcome.attempts]
            event.update(success=True, model_id=spec.model_id, plan_id=selected.plan_id,
                         artifact_id=selected.artifact_id, backend=selected.candidate.backend,
                         precision=selected.candidate.precision,
                         inference_ms=(time.perf_counter_ns() - execution_start) / 1e6,
                         attempts=attempts, fallback=outcome.fallback)
            if spec.quality_reference is not None:
                event["quality_reference"] = spec.quality_reference
                event["quality_drift"] = selected.quality_drift
            result = {"output": outcome.output, "plan": asdict(selected), "candidates": [asdict(c) for c in candidates],
                      "capabilities": asdict(profile), "metrics": event,
                      "attempts": attempts, "fallback": outcome.fallback,
                      "receipt": build_receipt_stub(selected, spec, event["request_id"],
                                                    executed=outcome.executed)}
            return result
        except Rejection as exc:
            event["error_code"] = exc.code
            if isinstance(exc, ExecutionFailed):
                event["attempts"] = [asdict(a) for a in exc.attempts]
                event["fallback"] = True
            raise
        except Exception:
            event["error_code"] = "EXECUTION_FAILED"
            raise
        finally:
            event["runtime_ms_excluding_telemetry_write"] = (time.perf_counter_ns() - start) / 1e6
            self.recorder.record(event)

    def _resolve_artifacts(self, selected, spec):
        """Resolve the plan's ranked artifacts into the cache and pin them
        for the flight, so eviction cannot take an artifact out from under
        an in-flight plan. Returns the artifact ids to unpin afterwards."""
        pinned = []
        for scored in selected.ranked:
            artifact = scored.artifact
            descriptor = {"artifact_id": artifact, "model_id": spec.model_id,
                          "precision": scored.candidate.precision,
                          "transform_version": transform_version(
                              scored.candidate.precision)}
            self.cache.get_or_build(
                artifact, artifact_size_bytes(spec.model_id,
                                              scored.candidate.precision),
                lambda descriptor=descriptor: descriptor)
            self.cache.pin(artifact)
            pinned.append(artifact)
        return pinned


def make_server(runtime, port=8000):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body):
            payload = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if self.path != "/infer":
                return self.respond(404, {"error": "NOT_FOUND"})
            self.connection.settimeout(5)
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise Rejection("INVALID_REQUEST", "Chunked requests unsupported")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    return self.respond(413, {"error": "INVALID_BODY_SIZE"})
                raw = json.loads(self.rfile.read(length))
                self.respond(200, runtime.infer(raw))
            except Rejection as exc:
                self.respond(422, {"error": exc.code, "message": str(exc)})
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "INVALID_JSON"})
            except Exception:
                self.respond(500, {"error": "INTERNAL_ERROR"})

    return HTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--telemetry", default="telemetry.jsonl")
    args = parser.parse_args()
    server = make_server(Runtime(args.telemetry), args.port)
    print(f"Local proof API: http://127.0.0.1:{server.server_port}/infer", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
