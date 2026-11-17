import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from aacl import *


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")
        self.runtime = Runtime(self.path)
        self.request = {"input": [1, 2, 3, 4]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_reference_result(self):
        result = self.runtime.infer(self.request)
        self.assertEqual(result["output"], {"score": 4.375, "label": 1})
        self.assertEqual(len(result["candidates"]), 2)

    def test_negative_class(self):
        self.assertEqual(self.runtime.infer({"input": [0, 0, 0, 0]})["output"]["label"], 0)

    def test_fp32_path(self):
        result = self.runtime.infer(dict(self.request, allowed_precisions=["fp32"]))
        self.assertEqual(result["plan"]["candidate"]["precision"], "fp32")
        self.assertEqual(result["output"]["score"], 4.375)

    def test_deterministic_plan(self):
        self.assertEqual(self.runtime.infer(self.request)["plan"], self.runtime.infer(self.request)["plan"])

    def test_invalid_inputs(self):
        for values in ([1], [True, 2, 3, 4], [float("nan"), 0, 0, 0], [1001, 0, 0, 0]):
            with self.subTest(values=values), self.assertRaises(Rejection):
                self.runtime.infer({"input": values})

    def test_unknown_model(self):
        with self.assertRaises(Rejection):
            self.runtime.infer(dict(self.request, model_id="missing"))

    def test_unsupported_constraint(self):
        with self.assertRaises(Rejection):
            self.runtime.infer(dict(self.request, max_memory_mb=1))

    def test_no_valid_plan(self):
        with self.assertRaisesRegex(Rejection, "No permitted"):
            self.runtime.infer(dict(self.request, allowed_precisions=["int8"]))

    def test_policy_denies_remote(self):
        spec = WorkloadSpec.parse(self.request)
        self.assertFalse(policy_allows(spec, ExecutionCandidate("remote-test", "fp64", False, 0)))
        with self.assertRaises(Rejection):
            plan(spec, BackendProfile(name="remote-test", local=False))

    def test_telemetry_without_input(self):
        self.runtime.infer(self.request)
        with self.assertRaises(Rejection):
            self.runtime.infer({"input": []})
        events = [json.loads(line) for line in Path(self.path).read_text().splitlines()]
        self.assertEqual([e["success"] for e in events], [True, False])
        self.assertNotIn("input", events[0])

    def test_artifact_integrity(self):
        selected, _ = plan(WorkloadSpec.parse(self.request), BackendProfile())
        with self.assertRaises(Rejection):
            CPUBackend().execute(ExecutionPlan("bad", selected.candidate, "wrong", "test"), (1, 2, 3, 4))

    def test_http(self):
        server = make_server(self.runtime, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/infer"
            request = urllib.request.Request(url, data=json.dumps(self.request).encode())
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["output"]["score"], 4.375)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url, data=b'{"input": []}'), timeout=5)
            self.assertEqual(error.exception.code, 422)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


class Phase1Tests(unittest.TestCase):
    """Contracts v2 (Phase 1): validated targets, the async handle contract,
    generalized artifact identity, the load/init telemetry split, plan
    explanations, and unsigned receipt stubs. The proof tests above are
    unmodified; everything Phase 1 adds is tested here."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")
        self.runtime = Runtime(self.path)
        self.request = {"input": [1, 2, 3, 4]}
        self.targeted = dict(self.request, latency_target_ms=50, memory_limit_mb=256,
                             cost_budget=0.01, optimize_for="quality",
                             quality_reference="linear-demo-reference-v1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_phase1_deterministic_plan(self):
        # The same request, planned twice, yields the identical plan:
        # same artifact id, same explanation, same selected candidate.
        spec = WorkloadSpec.parse(self.targeted)
        first, _ = plan(spec, BackendProfile())
        second, _ = plan(spec, BackendProfile())
        self.assertEqual(first, second)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.artifact_id, second.artifact_id)
        self.assertEqual(first.explanation, second.explanation)
        self.assertEqual(first.candidate, second.candidate)
        # And through the service path, the response's plan is identical too.
        self.assertEqual(self.runtime.infer(self.targeted)["plan"],
                         self.runtime.infer(self.targeted)["plan"])
        # Artifact identity is a real function of its inputs: precision is
        # part of the address, and dict ordering is not.
        # Phase 2 adaptation: this block originally compared `first` (the
        # targeted plan) against an fp32-only plan, because Phase 1's static
        # preference always chose fp64 for the targeted request. Phase 2's
        # target-pressure scorer genuinely chooses fp32 for it, so `first`
        # and the fp32-only plan now share an artifact id — correctly. The
        # distinctness check therefore compares the two single-precision
        # plans directly.
        from aacl.models.registry import SOURCE_DIGEST, TRANSFORM_VERSION
        fp32_spec = WorkloadSpec.parse(dict(self.request, allowed_precisions=["fp32"]))
        fp32_plan, _ = plan(fp32_spec, BackendProfile())
        fp64_spec = WorkloadSpec.parse(dict(self.request, allowed_precisions=["fp64"]))
        fp64_plan, _ = plan(fp64_spec, BackendProfile())
        self.assertNotEqual(fp32_plan.artifact_id, fp64_plan.artifact_id)
        self.assertEqual(
            artifact_id("m", SOURCE_DIGEST, "fp64", TRANSFORM_VERSION, {"a": 1, "b": 2}),
            artifact_id("m", SOURCE_DIGEST, "fp64", TRANSFORM_VERSION, {"b": 2, "a": 1}))

    def test_targets_validated_and_carried(self):
        spec = WorkloadSpec.parse(self.targeted)
        self.assertEqual(spec.latency_target_ms, 50.0)
        self.assertEqual(spec.memory_limit_mb, 256.0)
        self.assertEqual(spec.cost_budget, 0.01)
        self.assertEqual(spec.optimize_for, "quality")
        self.assertEqual(spec.quality_reference, "linear-demo-reference-v1")
        # Carried into the plan's explanation, named — never silently dropped.
        selected, _ = plan(spec, BackendProfile())
        for fragment in ("latency_target_ms=50.0", "memory_limit_mb=256.0",
                         "cost_budget=0.01", "optimize_for=quality",
                         "linear-demo-reference-v1"):
            self.assertIn(fragment, selected.explanation)
        # Invalid values are typed refusals, not quiet defaults.
        for bad in (dict(self.request, latency_target_ms=-5),
                    dict(self.request, latency_target_ms=0),
                    dict(self.request, memory_limit_mb=-1),
                    dict(self.request, cost_budget=-0.5),
                    dict(self.request, latency_target_ms="fast"),
                    dict(self.request, optimize_for="fastest"),
                    dict(self.request, quality_reference=""),
                    dict(self.request, quality_reference=42)):
            with self.subTest(bad=bad), self.assertRaises(Rejection):
                WorkloadSpec.parse(bad)

    def test_async_handle_contract(self):
        backend = CPUBackend()
        selected, _ = plan(WorkloadSpec.parse(self.request), backend.capabilities())
        handle = backend.submit(selected, (1, 2, 3, 4))
        self.assertEqual(handle.result(), {"score": 4.375, "label": 1})
        # One-chunk stream: the single result, whole.
        self.assertEqual(list(handle.stream()), [{"score": 4.375, "label": 1}])
        # Cancel is accepted and ignored — the work already finished — and
        # the handle says nothing was stopped.
        self.assertFalse(handle.cancel())
        self.assertEqual(handle.result(), {"score": 4.375, "label": 1})
        # A bad plan's error rides the handle and surfaces at result().
        bad = ExecutionPlan("bad", selected.candidate, "wrong", "test")
        with self.assertRaises(Rejection):
            backend.submit(bad, (1, 2, 3, 4)).result()

    def test_receipt_stub_unsigned(self):
        result = self.runtime.infer(self.request)
        receipt = result["receipt"]
        self.assertEqual(receipt["status"], "unsigned")
        self.assertIsNone(receipt["signature"])
        self.assertEqual(receipt["plan_id"], result["plan"]["plan_id"])
        self.assertEqual(receipt["artifact_id"], result["plan"]["artifact_id"])
        self.assertEqual(receipt["model_id"], "linear-demo-v1")

    def test_telemetry_load_init_split(self):
        self.runtime.infer(self.request)
        events = [json.loads(line) for line in Path(self.path).read_text().splitlines()]
        event = events[0]
        self.assertTrue(event["success"])
        self.assertIsInstance(event["init_ms"], float)
        self.assertIsInstance(event["load_ms"], float)
        self.assertGreaterEqual(event["init_ms"], 0)
        self.assertGreaterEqual(event["load_ms"], 0)
        self.assertEqual(event["artifact_id"],
                         self.runtime.infer(self.request)["plan"]["artifact_id"])


class Phase2Tests(unittest.TestCase):
    """Planning for real (Phase 2): CPU discovery, static candidate
    estimates, and target-pressure scoring. The proof tests are unmodified;
    one Phase 1 test was adapted (see test_phase1_deterministic_plan) because
    the scorer's replacement genuinely changed which precision the targeted
    request selects. Everything Phase 2 adds is tested here."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")
        self.runtime = Runtime(self.path)
        self.request = {"input": [1, 2, 3, 4]}
        self.profile = CPUBackend().capabilities()

    def tearDown(self):
        self.tmp.cleanup()

    def _latency_estimates(self):
        from aacl.planner.estimates import estimate
        spec = WorkloadSpec.parse(self.request)
        return {p: estimate(ExecutionCandidate("cpu-python", p, True, rank),
                            self.profile, spec).estimated_latency_ms
                for rank, p in enumerate(("fp64", "fp32"))}

    def test_phase2_discovery_facts(self):
        # Discovered facts about this machine — ranges and relations only,
        # never this machine's specific numbers.
        profile = self.profile
        self.assertGreaterEqual(profile.logical_cores, 1)
        self.assertGreater(profile.total_memory_bytes, 0)
        self.assertGreater(profile.available_memory_bytes, 0)
        self.assertLessEqual(profile.available_memory_bytes, profile.total_memory_bytes)
        self.assertGreater(profile.max_cache_bytes, 0)
        self.assertLessEqual(profile.max_cache_bytes, profile.total_memory_bytes)
        # The precision list is what the CPU backend genuinely implements.
        self.assertIn("fp32", profile.precisions)
        self.assertIn("fp64", profile.precisions)
        self.assertNotIn("int8", profile.precisions)
        # Discovery is one snapshot per process: profiles agree with
        # themselves, which is what keeps planning deterministic.
        self.assertEqual(BackendProfile(), BackendProfile())

    def test_phase2_two_candidate_choice(self):
        from aacl.planner import scorer
        estimates = self._latency_estimates()
        self.assertLess(estimates["fp32"], estimates["fp64"])
        # A latency target set between the two static estimates: fp64's
        # estimate breaks it, fp32's does not. Both candidates survive the
        # filter — the scorer, not the gate, makes this choice.
        target = (estimates["fp32"] + estimates["fp64"]) / 2
        spec = WorkloadSpec.parse(dict(self.request, latency_target_ms=target))
        selection = scorer.select(spec, self.profile,
                                  [ExecutionCandidate("cpu-python", "fp64", True, 0),
                                   ExecutionCandidate("cpu-python", "fp32", True, 1)])
        self.assertEqual(len(selection.scored), 2)
        self.assertEqual(selection.chosen.candidate.precision, "fp32")
        self.assertEqual(selection.reason, scorer.REASON)
        self.assertEqual(selection.chosen.binding_dimension, "latency")
        self.assertLess(selection.chosen.worst_pressure, 1.0)
        selected, _ = plan(spec, self.profile)
        self.assertEqual(selected.candidate.precision, "fp32")
        self.assertEqual(selected.estimated_latency_ms, estimates["fp32"])
        self.assertIn("% of its latency budget", selected.explanation)
        self.assertIn("static capability estimates", selected.explanation)
        # A loose target changes the pressures, not the ordering: fp32's
        # worst pressure is still the lower one.
        loose = WorkloadSpec.parse(dict(self.request,
                                        latency_target_ms=estimates["fp64"] * 100))
        selected, _ = plan(loose, self.profile)
        self.assertEqual(selected.candidate.precision, "fp32")

    def test_phase2_no_targets_keeps_standing_preference(self):
        from aacl.planner import scorer
        selected, _ = plan(WorkloadSpec.parse(self.request), self.profile)
        self.assertEqual(selected.candidate.precision, "fp64")
        self.assertEqual(selected.reason, scorer.NO_TARGET_REASON)
        self.assertIn("standing precision preference", selected.explanation)

    def test_phase2_deterministic_plan(self):
        # Same request, planned twice: identical plan — candidate, artifact,
        # estimates, and explanation all included.
        spec = WorkloadSpec.parse(dict(self.request, latency_target_ms=0.017,
                                       memory_limit_mb=256, cost_budget=0.01))
        first, _ = plan(spec, BackendProfile())
        second, _ = plan(spec, BackendProfile())
        self.assertEqual(first, second)
        self.assertEqual(first.estimated_latency_ms, second.estimated_latency_ms)
        self.assertEqual(first.estimated_memory_mb, second.estimated_memory_mb)
        self.assertEqual(first.estimated_cost, second.estimated_cost)
        self.assertEqual(first.explanation, second.explanation)
        self.assertEqual(self.runtime.infer(dict(self.request, latency_target_ms=0.017))["plan"],
                         self.runtime.infer(dict(self.request, latency_target_ms=0.017))["plan"])

    def test_phase2_quality_unmeasured(self):
        from aacl.planner import scorer
        estimates = self._latency_estimates()
        target = (estimates["fp32"] + estimates["fp64"]) / 2
        # optimize_for asks for quality and a reference is declared — and
        # neither moves the result: quality is unmeasured, so it contributes
        # no pressure, and the latency pressure still decides for fp32.
        spec = WorkloadSpec.parse(dict(self.request, latency_target_ms=target,
                                       optimize_for="quality",
                                       quality_reference="linear-demo-reference-v1"))
        selection = scorer.select(spec, self.profile,
                                  [ExecutionCandidate("cpu-python", "fp64", True, 0),
                                   ExecutionCandidate("cpu-python", "fp32", True, 1)])
        self.assertEqual(selection.chosen.candidate.precision, "fp32")
        for scored in selection.scored:
            self.assertEqual([dim for dim, _ in scored.pressures], ["latency"])
        selected, _ = plan(spec, self.profile)
        self.assertIn("quality is unmeasured", selected.explanation)
        self.assertIn("no pressure", selected.explanation)

    def test_phase2_tie_break_chain(self):
        # Controlled estimates (the estimator is stubbed) force exact
        # worst-pressure ties, so each step of the tie-break chain —
        # optimize_for, then absolute cost, then backend name, then
        # artifact id — can be watched deciding on its own.
        from unittest import mock
        from aacl.models.registry import SOURCE_DIGEST, TRANSFORM_VERSION
        from aacl.planner import scorer
        from aacl.planner.estimates import CandidateEstimate

        def run(spec, candidates, table):
            fake = lambda candidate, profile, spec: table[(candidate.backend,
                                                           candidate.precision)]
            with mock.patch("aacl.planner.scorer.estimate", side_effect=fake):
                return scorer.select(spec, self.profile, candidates)

        fp64 = ExecutionCandidate("cpu-python", "fp64", True, 0)
        fp32 = ExecutionCandidate("cpu-python", "fp32", True, 1)
        # Only a memory budget is declared, and both estimates sit at the
        # same memory pressure — worst pressures tie exactly.
        tied = {("cpu-python", "fp64"): CandidateEstimate(0.020, 50.0, 0.002),
                ("cpu-python", "fp32"): CandidateEstimate(0.010, 50.0, 0.001)}
        # optimize_for=quality: the standing precision *preference* speaks.
        spec = WorkloadSpec.parse(dict(self.request, memory_limit_mb=100,
                                       optimize_for="quality"))
        self.assertEqual(run(spec, [fp64, fp32], tied).chosen.candidate.precision, "fp64")
        # optimize_for=latency: the lower latency estimate wins the tie.
        spec = WorkloadSpec.parse(dict(self.request, memory_limit_mb=100,
                                       optimize_for="latency"))
        self.assertEqual(run(spec, [fp64, fp32], tied).chosen.candidate.precision, "fp32")
        # Backend name: identical candidates on two backends, identical
        # estimates — the alphabetically first backend wins.
        other = ExecutionCandidate("aaa-backend", "fp64", True, 0)
        both = {("cpu-python", "fp64"): CandidateEstimate(0.020, 50.0, 0.002),
                ("aaa-backend", "fp64"): CandidateEstimate(0.020, 50.0, 0.002)}
        spec = WorkloadSpec.parse(dict(self.request, memory_limit_mb=100,
                                       optimize_for="cost"))
        self.assertEqual(run(spec, [fp64, other], both).chosen.candidate.backend,
                         "aaa-backend")
        # Artifact id: same backend, same estimates, same cost — the lower
        # artifact id wins.
        same = {("cpu-python", "fp64"): CandidateEstimate(0.010, 50.0, 0.001),
                ("cpu-python", "fp32"): CandidateEstimate(0.010, 50.0, 0.001)}
        selection = run(spec, [fp64, fp32], same)
        expected = min((fp64, fp32),
                       key=lambda c: artifact_id("linear-demo-v1", SOURCE_DIGEST,
                                                 c.precision, TRANSFORM_VERSION,
                                                 {"backend": c.backend}))
        self.assertEqual(selection.chosen.candidate, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
