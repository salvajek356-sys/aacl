"""Phase 5 demo: two backends, one runtime, and an honest verdict.

Prints the discovered profiles, runs a fixed request set through the
Runtime, and — where a GPU genuinely exists — cross-checks CPU and GPU
outputs on identical inputs. The verdict is computed, not asserted:

- PASS    a GPU is present, the planner chose each backend for at
          least one workload in the set, and every cross-check agrees.
- PARTIAL no GPU is present (the CPU portions ran; the GPU is reported
          unavailable), or a GPU is present but one backend took every
          workload in the set — the static estimates may honestly make
          one dominate, and the demo says which and why that is a
          finding about the estimates, not a pass.
- FAIL    a check that could run, failed.

On a machine without a GPU this prints PARTIAL. It will never print
PASS there. That is the point.
"""
import sys
from dataclasses import replace

from aacl import Runtime, WorkloadSpec, plan
from aacl.backends import discovery
from aacl.backends.cpu import CPUBackend
from aacl.models.registry import artifact_id, source_digest, transform_version

REQUESTS = [
    ("Demo model, no targets — the standing preference",
     {"input": [1, 2, 3, 4]}),
    ("Demo model, latency target 0.017 ms — fp32 territory",
     {"input": [1, 2, 3, 4], "latency_target_ms": 0.017}),
    ("Demo model, fp64 only, latency target 0.018 ms — the CPU's "
     "fp64 estimate breaks it, the GPU's does not",
     {"input": [1, 2, 3, 4], "allowed_precisions": ["fp64"],
      "latency_target_ms": 0.018}),
    ("Iris, latency target 0.03 ms",
     {"model_id": "iris-logreg-v1", "input": [5.1, 3.5, 1.4, 0.2],
      "latency_target_ms": 0.03}),
    ("Iris, memory limit 32 MB — smaller than a device context",
     {"model_id": "iris-logreg-v1", "input": [5.1, 3.5, 1.4, 0.2],
      "memory_limit_mb": 32}),
]

CROSS_CHECKS = [
    ({"input": [1, 2, 3, 4]}, "fp64"),
    ({"input": [1, 2, 3, 4]}, "fp32"),
    ({"model_id": "iris-logreg-v1", "input": [5.1, 3.5, 1.4, 0.2]}, "fp64"),
    ({"model_id": "iris-logreg-v1", "input": [5.1, 3.5, 1.4, 0.2]}, "fp32"),
]

SCORE_TOLERANCE = 1e-5  # fp32 tolerance; labels must match exactly


def _forced_plan(spec, backend_name, precision):
    base, candidates = plan(spec, CPUBackend().capabilities())
    candidate = next(c for c in candidates
                     if c.backend == backend_name and c.precision == precision)
    artifact = artifact_id(spec.model_id, source_digest(spec.model_id),
                           precision, transform_version(precision),
                           {"backend": backend_name})
    return replace(base, candidate=candidate, artifact_id=artifact)


def main():
    failures = []
    profiles = discovery.registered_profiles()
    backends = discovery.registered_backends()
    gpu_names = [n for n in backends if n != "cpu-python"]

    print("Discovered profiles:")
    for profile in profiles:
        print(f"  {profile.name}: architecture={profile.architecture}, "
              f"cores={profile.logical_cores}, "
              f"total_memory={profile.total_memory_bytes} B, "
              f"max_cache={profile.max_cache_bytes} B, "
              f"precisions={list(profile.precisions)}, local={profile.local}")
    if not gpu_names:
        print("  GPU: unavailable — discovery found no device "
              "(torch absent, or no device answering).")
    print()

    runtime = Runtime(None)
    chosen_backends = set()
    print("Fixed request set, through the Runtime:")
    for label, raw in REQUESTS:
        try:
            result = runtime.infer(raw)
        except Exception as exc:
            failures.append(f"{label}: runtime raised {exc!r}")
            print(f"  {label}\n    FAILED: {exc!r}")
            continue
        candidate = result["plan"]["candidate"]
        chosen_backends.add(candidate["backend"])
        print(f"  {label}\n    chose {candidate['backend']}/"
              f"{candidate['precision']} -> {result['output']}")
    print()

    if gpu_names:
        gpu_name = gpu_names[0]
        gpu = backends[gpu_name]
        cpu = CPUBackend()
        print(f"Cross-checks, CPU vs {gpu_name} on identical inputs:")
        for raw, precision in CROSS_CHECKS:
            spec = WorkloadSpec.parse(raw)
            try:
                cpu_out = cpu.submit(_forced_plan(spec, "cpu-python", precision),
                                     spec.input).result()
                gpu_out = gpu.submit(_forced_plan(spec, gpu_name, precision),
                                     spec.input).result()
            except Exception as exc:
                failures.append(f"cross-check {raw} {precision}: {exc!r}")
                print(f"  {spec.model_id} {precision}: FAILED: {exc!r}")
                continue
            cpu_scores = cpu_out.get("scores", [cpu_out["score"]])
            gpu_scores = gpu_out.get("scores", [gpu_out["score"]])
            worst = max(abs(g - c) for g, c in zip(gpu_scores, cpu_scores))
            agree = (gpu_out["label"] == cpu_out["label"]
                     and worst <= SCORE_TOLERANCE)
            if not agree:
                failures.append(
                    f"cross-check {spec.model_id} {precision}: labels "
                    f"{gpu_out['label']} vs {cpu_out['label']}, worst "
                    f"score difference {worst}")
            print(f"  {spec.model_id} {precision}: labels "
                  f"{gpu_out['label']} == {cpu_out['label']}, worst score "
                  f"difference {worst:.3g} -> {'agree' if agree else 'DISAGREE'}")
        print()

    if failures:
        verdict = "FAIL"
        detail = "; ".join(failures)
    elif not gpu_names:
        verdict = "PARTIAL"
        detail = ("no GPU on this machine: the CPU portions ran and the "
                  "planner's choices above are the one-backend choices. "
                  "The GPU half of this demo runs in the Strix session "
                  "(docs/phase5-strix-runbook.md).")
    elif chosen_backends == {"cpu-python"} or chosen_backends == set(gpu_names):
        verdict = "PARTIAL"
        detail = (f"one backend took every workload in the set "
                  f"({sorted(chosen_backends)}): the static estimates make "
                  f"it dominate these requests. That is a finding about "
                  f"the placeholder estimates, to be revisited when "
                  f"Phase 6 replaces them with measured corrections — "
                  f"not a pass.")
    else:
        verdict = "PASS"
        detail = ("the planner chose each backend for at least one "
                  "workload, and every cross-check agreed.")
    print(f"Verdict: {verdict} — {detail}")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
