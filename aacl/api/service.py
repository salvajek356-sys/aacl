"""The thin application-facing API (roadmap §12): POST /infer, kept boring on
purpose. Runtime flow, error codes, status codes, and body limits are the
v0.1 proof's, unchanged.

Phase 1: execution goes through the backend's async handle contract
(submit → result), the response gains the plan's explanation (inside the
plan) and an unsigned receipt stub, and telemetry records the load/init
timing split.
"""
import argparse
import json
import time
import uuid
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..backends.cpu import CPUBackend
from ..core.workload import Rejection, WorkloadSpec
from ..planner.planner import plan
from ..telemetry import metrics
from ..telemetry.receipt import build_receipt_stub
from ..telemetry.recorder import TelemetryRecorder


class Runtime:
    def __init__(self, telemetry_path="telemetry.jsonl"):
        self.backend = CPUBackend()
        self.telemetry_path = telemetry_path
        self.recorder = TelemetryRecorder(telemetry_path)

    def infer(self, raw):
        start = time.perf_counter_ns()
        event = metrics.new_event(str(uuid.uuid4()))
        try:
            init_start = time.perf_counter_ns()
            profile = self.backend.capabilities()
            event["init_ms"] = (time.perf_counter_ns() - init_start) / 1e6
            load_start = time.perf_counter_ns()
            spec = WorkloadSpec.parse(raw)
            selected, candidates = plan(spec, profile)
            event["load_ms"] = (time.perf_counter_ns() - load_start) / 1e6
            execution_start = time.perf_counter_ns()
            output = self.backend.submit(selected, spec.input).result()
            event.update(success=True, model_id=spec.model_id, plan_id=selected.plan_id,
                         artifact_id=selected.artifact_id, backend=selected.candidate.backend,
                         precision=selected.candidate.precision,
                         inference_ms=(time.perf_counter_ns() - execution_start) / 1e6)
            result = {"output": output, "plan": asdict(selected), "candidates": [asdict(c) for c in candidates],
                      "capabilities": asdict(profile), "metrics": event,
                      "receipt": build_receipt_stub(selected, spec, event["request_id"])}
            return result
        except Rejection as exc:
            event["error_code"] = exc.code
            raise
        except Exception:
            event["error_code"] = "EXECUTION_FAILED"
            raise
        finally:
            event["runtime_ms_excluding_telemetry_write"] = (time.perf_counter_ns() - start) / 1e6
            self.recorder.record(event)


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
