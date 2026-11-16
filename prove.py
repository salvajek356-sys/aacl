"""Run reproducible functional evidence and a descriptive microbenchmark."""
import contextlib
import datetime
import io
import json
import platform
import random
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path
from aacl import Runtime, CPUBackend, WorkloadSpec, plan


def summarize(values):
    values = sorted(values)
    return {"median_us": statistics.median(values), "p95_us": values[int(.95 * (len(values)-1))]}


def main():
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Run this proof inside a Python virtual environment")
    output = Path("evidence")
    output.mkdir(exist_ok=True)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(".", pattern="test_aacl.py")
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (output / "tests.txt").write_text(stream.getvalue())
    if not tests.wasSuccessful():
        print(stream.getvalue())
        raise SystemExit(1)
    raw = {"input": [1, 2, 3, 4]}
    runtime = Runtime(None)
    backend = CPUBackend()
    spec = WorkloadSpec.parse(raw)
    selected, _ = plan(spec, backend.capabilities())
    rng = random.Random(42)
    errors, disagreements = [], 0
    for _ in range(1000):
        values = [rng.uniform(-10, 10) for _ in range(4)]
        reference = runtime.infer({"input": values})["output"]
        reduced = runtime.infer({"input": values, "allowed_precisions": ["fp32"]})["output"]
        errors.append(abs(reference["score"] - reduced["score"]))
        disagreements += reference["label"] != reduced["label"]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        recorded = Runtime(str(Path(directory) / "telemetry.jsonl"))
        functions = {"direct_cpu_fp64": lambda: backend.execute(selected, spec.input),
                     "runtime_no_telemetry_write": lambda: runtime.infer(raw),
                     "runtime_with_jsonl_write": lambda: recorded.infer(raw)}
        for name, function in functions.items():
            for _ in range(100):
                function()
            durations = []
            for _ in range(2000):
                start = time.perf_counter_ns()
                function()
                durations.append((time.perf_counter_ns() - start) / 1000)
            results[name] = summarize(durations)
    report = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.platform(),
              "virtual_environment": sys.prefix != sys.base_prefix,
              "third_party_dependencies": [], "tests_run": tests.testsRun, "tests_passed": True,
              "benchmark_iterations_per_path": 2000, "warmups_per_path": 100,
              "benchmark": results,
              "synthetic_precision_comparison": {"samples": 1000, "seed": 42,
                  "max_absolute_score_error": max(errors), "label_disagreements": disagreements},
              "limitations": ["Fixed hand-authored model, not trained-model accuracy validation",
                  "fp32 explicitly rounded in Python; no native acceleration or int8",
                  "Microbenchmark excludes HTTP and model load; tiny model exaggerates orchestration overhead",
                  "Policy remote denial uses a synthetic candidate; no remote execution",
                  "No GPU, NPU, resource enforcement, production concurrency, or fallback"]}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    demo = Runtime(str(output / "demo-telemetry.jsonl")).infer(raw)
    (output / "example-response.json").write_text(json.dumps(demo, indent=2) + "\n")
    print(stream.getvalue())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
