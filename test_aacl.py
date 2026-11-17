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
        # Phase 5 adaptation: this count was written when one backend
        # existed. Candidate generation now enumerates every registered
        # backend's float paths — two per backend — so the count is
        # relative to the registry. On a CPU-only machine it is the
        # original 2, unchanged.
        from aacl.backends import discovery
        self.assertEqual(len(result["candidates"]),
                         2 * len(discovery.registered_profiles()))

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
        # Phase 4 adaptation: this request originally declared
        # quality_reference="linear-demo-reference-v1" — a placeholder name
        # Phase 1–3 carried without measuring. Phase 4 makes references
        # real: a name must be a registered eval set for the requested
        # model, or the request is refused. The targeted request therefore
        # names the trained model and its actual reference, iris-eval-v1;
        # what the Phase 1 tests assert about it (targets validated,
        # carried, and named in the explanation) is unchanged.
        self.targeted = dict(self.request, model_id="iris-logreg-v1",
                             latency_target_ms=50, memory_limit_mb=256,
                             cost_budget=0.01, optimize_for="quality",
                             quality_reference="iris-eval-v1")

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
        # Phase 4 adaptation: the reference name is the trained model's
        # registered eval set (see setUp); the assertion's substance —
        # the declared reference is carried, not dropped — is unchanged.
        self.assertEqual(spec.quality_reference, "iris-eval-v1")
        # Carried into the plan's explanation, named — never silently dropped.
        selected, _ = plan(spec, BackendProfile())
        for fragment in ("latency_target_ms=50.0", "memory_limit_mb=256.0",
                         "cost_budget=0.01", "optimize_for=quality",
                         "iris-eval-v1"):
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
    request selects. Everything Phase 2 adds is tested here.

    Phase 4 adapted two tests in this class, with reasons recorded inline:
    test_phase2_discovery_facts (int8 is now genuinely implemented) and
    test_phase2_quality_unmeasured (reference names must now be real).
    Phase 4 also adapted Phase1Tests' targeted request to name the trained
    model's registered reference."""

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
        # Phase 4 adaptation: this asserted int8's absence, which was the
        # truth in Phase 2 — no backend offered it. Phase 4's CPU backend
        # genuinely executes int8 (integer accumulation over the
        # transformation service's artifacts), so the honest list now
        # includes it; it is offered as a candidate only for models with
        # a registered transform.
        self.assertIn("int8", profile.precisions)
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
        # optimize_for asks for quality — and it does not move the result:
        # quality is unmeasured, so it contributes no pressure, and the
        # latency pressure still decides for fp32.
        # Phase 4 adaptation: this test originally also declared
        # quality_reference="linear-demo-reference-v1", a placeholder name
        # Phase 2 carried without measuring. Phase 4 refuses names that
        # are not registered eval sets (Phase4Tests covers the refusal),
        # so the unmeasured path is exercised the way it now occurs — no
        # reference declared — and the explanation's sentence is Phase 4's
        # exact wording. The claim under test is unchanged.
        spec = WorkloadSpec.parse(dict(self.request, latency_target_ms=target,
                                       optimize_for="quality"))
        selection = scorer.select(spec, self.profile,
                                  [ExecutionCandidate("cpu-python", "fp64", True, 0),
                                   ExecutionCandidate("cpu-python", "fp32", True, 1)])
        self.assertEqual(selection.chosen.candidate.precision, "fp32")
        for scored in selection.scored:
            self.assertEqual([dim for dim, _ in scored.pressures], ["latency"])
        selected, _ = plan(spec, self.profile)
        self.assertIn("quality unmeasured — no reference", selected.explanation)
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


class LyingBackend:
    """Fault injection: claims fp64 and fp32 in its profile, then rejects
    fp64 at execution — a capability lie — while running fp32 honestly,
    with the CPU backend's own math."""

    def capabilities(self):
        return BackendProfile(name="liar-cpu", precisions=("fp64", "fp32"), local=True)

    def submit(self, selected, values):
        try:
            return CompletedHandle(output=self._run(selected, values))
        except Exception as exc:
            return CompletedHandle(error=exc)

    def _run(self, selected, values):
        from aacl.backends.cpu import f32
        from aacl.models.registry import MODEL, SOURCE_DIGEST, TRANSFORM_VERSION
        expected = artifact_id(MODEL["id"], SOURCE_DIGEST,
                               selected.candidate.precision, TRANSFORM_VERSION,
                               {"backend": "liar-cpu"})
        if selected.artifact_id != expected or selected.candidate.backend != "liar-cpu":
            raise Rejection("INVALID_PLAN", "Artifact or backend mismatch")
        if selected.candidate.precision == "fp64":
            raise CapabilityLie("liar-cpu claims fp64 but rejects it at execution")
        score = f32(MODEL["bias"])
        for weight, value in zip(MODEL["weights"], values):
            score = f32(score + f32(f32(weight) * f32(value)))
        return {"score": score, "label": int(score >= 0)}


class AlwaysFailingBackend:
    """Fault injection: advertises both precisions and fails every
    execution with an ordinary backend error."""

    def capabilities(self):
        return BackendProfile(name="always-fails", precisions=("fp64", "fp32"), local=True)

    def submit(self, selected, values):
        return CompletedHandle(error=RuntimeError("always-fails cannot execute"))


class Phase3Tests(unittest.TestCase):
    """Fallback protocol + artifact lifecycle (Phase 3): ranked plans, the
    executor, failure classes, reliability downgrades, per-attempt
    telemetry, and the artifact cache. All prior tests are unmodified;
    everything Phase 3 adds is tested here."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")
        self.request = {"input": [1, 2, 3, 4]}

    def tearDown(self):
        self.tmp.cleanup()

    def _events(self):
        return [json.loads(line) for line in Path(self.path).read_text().splitlines()]

    def test_plan_carries_ranked_survivors(self):
        spec = WorkloadSpec.parse(self.request)
        selected, _ = plan(spec, BackendProfile())
        # Phase 5 adaptation: the ranked count was written when one
        # backend existed; the plan now ranks every registered backend's
        # survivors — two float paths per backend for this model. On a
        # CPU-only machine it is the original 2, unchanged.
        from aacl.backends import discovery
        self.assertEqual(len(selected.ranked),
                         2 * len(discovery.registered_profiles()))
        self.assertEqual(selected.ranked[0].candidate, selected.candidate)
        self.assertEqual(selected.ranked[0].artifact, selected.artifact_id)
        # A targeted request ranks in the scorer's order, best first.
        targeted, _ = plan(WorkloadSpec.parse(dict(self.request, latency_target_ms=0.017)),
                           BackendProfile())
        # Phase 5 adaptation: with a second backend registered, the
        # ranked list interleaves backends; the claim under test — the
        # passed profile's own paths rank fp32 before fp64 — is asserted
        # on that backend's subsequence. Identical on a CPU-only machine.
        self.assertEqual([s.candidate.precision for s in targeted.ranked
                          if s.candidate.backend == "cpu-python"],
                         ["fp32", "fp64"])

    def test_capability_lie_advances_and_downgrades(self):
        runtime = Runtime(self.path, backend=LyingBackend())
        # First request: no targets, so the standing preference plans fp64.
        # The backend lies on fp64; the executor advances to fp32 and the
        # request still succeeds — on the fallback, recorded as one.
        result = runtime.infer(self.request)
        self.assertEqual(result["output"], {"score": 4.375, "label": 1})
        self.assertTrue(result["fallback"])
        attempts = result["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["precision"], "fp64")
        self.assertEqual(attempts[0]["outcome"], "failed")
        self.assertEqual(attempts[0]["failure_class"], "CAPABILITY_LIE")
        self.assertEqual(attempts[1]["precision"], "fp32")
        self.assertEqual(attempts[1]["outcome"], "succeeded")
        self.assertIsNone(attempts[1]["failure_class"])
        # The receipt names what actually ran, under the plan's id.
        self.assertEqual(result["receipt"]["precision"], "fp32")
        self.assertEqual(result["receipt"]["plan_id"], result["plan"]["plan_id"])
        # The downgrade lands on the registry entry for the capability that
        # lied — that backend, that model, that precision — and not on fp32.
        self.assertTrue(runtime.reliability.is_downgraded(
            "liar-cpu", "linear-demo-v1", "fp64"))
        self.assertEqual(runtime.reliability.lies(
            "liar-cpu", "linear-demo-v1", "fp64"), 1)
        self.assertFalse(runtime.reliability.is_downgraded(
            "liar-cpu", "linear-demo-v1", "fp32"))
        # Per-attempt telemetry: both attempts are in the request's event.
        events = self._events()
        self.assertEqual(len(events[0]["attempts"]), 2)
        self.assertEqual(events[0]["attempts"][0]["failure_class"], "CAPABILITY_LIE")
        self.assertTrue(events[0]["fallback"])
        self.assertTrue(events[0]["success"])
        # The next plan visibly avoids the downgraded entry: fp32 is chosen
        # directly, the explanation names the downgrade, and no fallback
        # is needed.
        second = runtime.infer(self.request)
        self.assertEqual(second["plan"]["candidate"]["precision"], "fp32")
        self.assertIn("downgraded", second["plan"]["explanation"])
        self.assertIn("capability lie", second["plan"]["explanation"])
        self.assertFalse(second["fallback"])
        self.assertEqual(len(second["attempts"]), 1)

    def test_downgraded_candidate_is_last_resort_not_excluded(self):
        runtime = Runtime(self.path, backend=LyingBackend())
        runtime.infer(self.request)  # the lie, and the downgrade
        spec = WorkloadSpec.parse(dict(self.request, allowed_precisions=["fp64"]))
        selected, _ = plan(spec, runtime.backend.capabilities(),
                           reliability=runtime.reliability)
        self.assertEqual(selected.candidate.precision, "fp64")
        self.assertTrue(selected.ranked[0].downgraded)
        self.assertIn("last resort", selected.explanation)

    def test_policy_regated_per_attempt_and_total_failure(self):
        runtime = Runtime(self.path, backend=LyingBackend())
        # A gate that denies fp32 at execution time. The planner admitted
        # both candidates under the standing policy; the executor consults
        # the gate again for each attempt — and the denial is an attempt,
        # recorded, not an execution.
        gate = lambda spec, candidate: candidate.precision != "fp32"
        executor = Executor(runtime.backend, reliability=runtime.reliability,
                            policy_gate=gate)
        spec = WorkloadSpec.parse(self.request)
        selected, _ = plan(spec, runtime.backend.capabilities(),
                           reliability=runtime.reliability)
        with self.assertRaises(ExecutionFailed) as failure:
            executor.execute(selected, spec, spec.input)
        attempts = failure.exception.attempts
        self.assertEqual([a.failure_class for a in attempts],
                         ["CAPABILITY_LIE", "POLICY_DENIAL"])
        self.assertEqual(attempts[1].outcome, "denied")
        # The typed error names every attempt and its failure class.
        self.assertIn("CAPABILITY_LIE", str(failure.exception))
        self.assertIn("POLICY_DENIAL", str(failure.exception))
        self.assertEqual(failure.exception.code, "EXECUTION_FAILED")

    def test_total_failure_through_runtime_records_every_attempt(self):
        runtime = Runtime(self.path, backend=AlwaysFailingBackend())
        with self.assertRaises(ExecutionFailed):
            runtime.infer(self.request)
        event = self._events()[0]
        self.assertFalse(event["success"])
        self.assertEqual(event["error_code"], "EXECUTION_FAILED")
        self.assertTrue(event["fallback"])
        self.assertEqual(len(event["attempts"]), 2)
        self.assertEqual([a["failure_class"] for a in event["attempts"]],
                         ["BACKEND_ERROR", "BACKEND_ERROR"])

    def test_attempts_are_bounded(self):
        from aacl.core.executor import MAX_ATTEMPTS
        from aacl.planner import scorer
        # Ten candidates, one plan, an always-failing backend: the executor
        # stops at the bound instead of walking the whole ranked list.
        spec = WorkloadSpec.parse(self.request)
        candidates = [ExecutionCandidate(f"backend-{i}", "fp32", True, 0)
                      for i in range(MAX_ATTEMPTS + 2)]
        selection = scorer.select(spec, BackendProfile(), candidates)
        self.assertEqual(len(selection.ranked), MAX_ATTEMPTS + 2)
        selected = ExecutionPlan("bounded", selection.chosen.candidate,
                                 selection.chosen.artifact, "test",
                                 ranked=selection.ranked)
        with self.assertRaises(ExecutionFailed) as failure:
            Executor(AlwaysFailingBackend()).execute(selected, spec, spec.input)
        self.assertEqual(len(failure.exception.attempts), MAX_ATTEMPTS)

    def test_cache_builds_once_and_evicts_lru(self):
        cache = ArtifactCache(100)
        built = []

        def build(tag):
            return lambda: built.append(tag) or {"tag": tag}

        first = cache.get_or_build("a", 40, build("a"))
        cache.get_or_build("b", 40, build("b"))
        # A hit serves the cached artifact and does not rebuild — and it
        # refreshes "a", which decides the eviction below.
        self.assertIs(cache.get_or_build("a", 40, build("a")), first)
        self.assertEqual(built, ["a", "b"])
        cache.get_or_build("c", 40, build("c"))  # 120 > 100: "b" goes, not "a"
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)
        self.assertIn("c", cache)
        self.assertEqual(cache.bytes_used, 80)

    def test_cache_pinning_survives_eviction(self):
        cache = ArtifactCache(100)
        cache.get_or_build("a", 40, lambda: "A")
        cache.get_or_build("b", 40, lambda: "B")
        cache.pin("a")
        cache.get_or_build("c", 40, lambda: "C")  # only "b" is evictable
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)
        self.assertTrue(cache.is_pinned("a"))
        cache.unpin("a")
        cache.get_or_build("d", 40, lambda: "D")  # now "a" is the LRU entry
        self.assertNotIn("a", cache)
        self.assertIn("c", cache)
        self.assertIn("d", cache)

    def test_cache_oversize_artifact_built_but_not_retained(self):
        cache = ArtifactCache(100)
        self.assertEqual(cache.get_or_build("big", 200, lambda: "BIG"), "BIG")
        self.assertNotIn("big", cache)
        self.assertEqual(cache.bytes_used, 0)
        # Pinning an artifact the cache does not hold is a no-op, not an error.
        cache.pin("big")
        self.assertFalse(cache.is_pinned("big"))

    def test_runtime_cache_resolves_and_unpins_plan_artifacts(self):
        runtime = Runtime(self.path)
        result = runtime.infer(self.request)
        # Every ranked artifact was resolved into the runtime's cache,
        # bounded by the discovered profile's ceiling...
        # Phase 5 adaptation: the count was the literal 2 of a
        # one-backend world; the claim is that the cache holds the
        # plan's ranked artifacts, however many the registry produced.
        self.assertEqual(len(runtime.cache), len(result["plan"]["ranked"]))
        self.assertLessEqual(runtime.cache.bytes_used, runtime.cache.max_bytes)
        # ...and unpinned when the flight ended, so eviction may take them.
        for scored in result["plan"]["ranked"]:
            self.assertFalse(runtime.cache.is_pinned(scored["artifact"]))


class Phase4Tests(unittest.TestCase):
    """Quantization + measured quality (Phase 4): a genuinely trained
    model, the transformation service and its int8 artifact, drift
    measured against the named reference iris-eval-v1, and quality
    pressure in the minimax. Adaptations to earlier tests are recorded
    where they happened (Phase1Tests.setUp, two Phase2Tests); every other
    prior test is unmodified."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")
        self.runtime = Runtime(self.path)
        self.profile = CPUBackend().capabilities()
        from aacl.models.iris_data import EVAL_ROWS
        self.an_input = list(EVAL_ROWS[0][0])
        self.base = {"model_id": "iris-logreg-v1", "input": self.an_input}

    def tearDown(self):
        self.tmp.cleanup()

    def test_training_reproduces_committed_weights(self):
        # The committed weights are a claim; retraining is the check.
        # Same dataset, same frozen recipe — the floats must agree
        # exactly, not approximately.
        from aacl.models import iris
        weights, bias = iris.train()
        self.assertEqual(weights, iris.TRAINED_WEIGHTS)
        self.assertEqual(bias, iris.TRAINED_BIAS)

    def test_trained_model_accuracy(self):
        # The trained model's fp64 accuracy on the held-out eval split:
        # 29 of 30 (the one miss is a versicolor/virginica boundary row).
        from aacl.models import iris
        from aacl.models.iris_data import EVAL_ROWS, TRAIN_ROWS
        eval_correct = sum(1 for x, y in EVAL_ROWS
                           if iris.label(iris.TRAINED_WEIGHTS,
                                         iris.TRAINED_BIAS, x) == y)
        train_correct = sum(1 for x, y in TRAIN_ROWS
                            if iris.label(iris.TRAINED_WEIGHTS,
                                          iris.TRAINED_BIAS, x) == y)
        self.assertEqual(eval_correct, 29)
        self.assertGreaterEqual(eval_correct / len(EVAL_ROWS), 0.9)
        self.assertGreaterEqual(train_correct / len(TRAIN_ROWS), 0.95)

    def test_int8_artifact_identity_and_build(self):
        from aacl.models.registry import (source_digest, transform_version)
        from aacl.optimization import quantization
        self.assertEqual(transform_version("int8"), "int8-v1")
        self.assertEqual(transform_version("fp32"), "identity-v1")
        artifact = quantization.build_int8_artifact("iris-logreg-v1")
        # The artifact is genuinely integer: every stored weight an int
        # in int8 range, and rebuilding reproduces it exactly.
        for row in artifact["weight_ints"]:
            for value in row:
                self.assertIsInstance(value, int)
                self.assertGreaterEqual(value, -127)
                self.assertLessEqual(value, 127)
        self.assertEqual(quantization.build_int8_artifact("iris-logreg-v1"),
                         artifact)
        # Its identity differs from the floating-point artifacts' — the
        # transform version is part of the address.
        digest = source_digest("iris-logreg-v1")
        int8_id = artifact_id("iris-logreg-v1", digest, "int8",
                              transform_version("int8"), {"backend": "cpu-python"})
        fp32_id = artifact_id("iris-logreg-v1", digest, "fp32",
                              transform_version("fp32"), {"backend": "cpu-python"})
        self.assertNotEqual(int8_id, fp32_id)
        # The demo model has no calibration data, so no transform exists
        # for it — and its int8 request still finds no valid plan.
        self.assertFalse(quantization.has_transform("linear-demo-v1"))
        with self.assertRaises(Rejection):
            self.runtime.infer({"input": [1, 2, 3, 4],
                                "allowed_precisions": ["int8"]})

    def test_int8_execution_through_runtime(self):
        from aacl.models.iris_data import CLASSES
        from aacl.optimization import quantization
        result = self.runtime.infer(dict(self.base, allowed_precisions=["int8"]))
        self.assertEqual(result["plan"]["candidate"]["precision"], "int8")
        artifact = quantization.build_int8_artifact("iris-logreg-v1")
        expected_scores = quantization.execute_int8(artifact, tuple(self.an_input))
        self.assertEqual(result["output"]["scores"], expected_scores)
        expected_label = max(range(3), key=lambda c: expected_scores[c])
        self.assertEqual(result["output"]["label"], expected_label)
        self.assertEqual(result["output"]["label_name"], CLASSES[expected_label])

    def test_drift_measured_deterministic_and_recorded(self):
        from aacl.optimization.quality import measure_drift
        # Computed, and the same computation twice: identical figures.
        first = measure_drift("iris-logreg-v1", "int8", "iris-eval-v1")
        second = measure_drift("iris-logreg-v1", "int8", "iris-eval-v1")
        self.assertEqual(first, second)
        self.assertEqual(first["eval_samples"], 30)
        # fp64 against itself measures exactly zero — by running it.
        fp64 = measure_drift("iris-logreg-v1", "fp64", "iris-eval-v1")
        self.assertEqual(fp64["mean_score_error"], 0.0)
        self.assertEqual(fp64["label_disagreements"], 0)
        # The measured ordering on this eval set: fp32's score error is
        # five orders below int8's; neither flips a label here, which is
        # exactly why the tolerance is defined on score error.
        fp32 = measure_drift("iris-logreg-v1", "fp32", "iris-eval-v1")
        self.assertGreater(fp32["mean_score_error"], 0.0)
        self.assertLess(fp32["mean_score_error"], first["mean_score_error"])
        self.assertGreater(first["max_score_error"], 0.1)
        self.assertEqual(first["label_disagreements"], 0)
        # Recorded per run: on the plan and in the telemetry event.
        result = self.runtime.infer(dict(self.base,
                                         quality_reference="iris-eval-v1"))
        chosen_precision = result["plan"]["candidate"]["precision"]
        expected = measure_drift("iris-logreg-v1", chosen_precision,
                                 "iris-eval-v1")
        self.assertEqual(result["plan"]["quality_drift"], expected)
        events = [json.loads(line) for line in Path(self.path).read_text().splitlines()]
        self.assertEqual(events[0]["quality_reference"], "iris-eval-v1")
        self.assertEqual(events[0]["quality_drift"], expected)

    def test_planner_chooses_int8_under_loose_drift_tolerance(self):
        # Same model, same input: a tight latency target fp32 cannot meet
        # and a drift tolerance int8's measured error sits well inside.
        # (The workload opts into int8 explicitly — allowed_precisions is
        # an allow-list, and its default remains the proof's fp32/fp64.)
        spec = WorkloadSpec.parse(dict(self.base, latency_target_ms=0.015,
                                       allowed_precisions=["fp64", "fp32", "int8"],
                                       quality_reference="iris-eval-v1",
                                       quality_max_drift=0.1))
        selected, _ = plan(spec, self.profile)
        self.assertEqual(selected.candidate.precision, "int8")
        self.assertIn("% of its latency budget", selected.explanation)
        for scored in selected.ranked:
            self.assertIn("quality", dict(scored.pressures))
        int8 = next(s for s in selected.ranked
                    if s.candidate.precision == "int8")
        self.assertLess(dict(int8.pressures)["quality"], 1.0)
        self.assertEqual(selected.quality_drift["label_disagreements"],
                         int8.drift["label_disagreements"])

    def test_planner_chooses_fp32_under_tight_drift_tolerance(self):
        # Only the tolerance changes: int8's measured drift now blows its
        # quality budget several times over, and fp32 — whose measured
        # error is five orders smaller — wins despite the latency target.
        spec = WorkloadSpec.parse(dict(self.base, latency_target_ms=0.015,
                                       allowed_precisions=["fp64", "fp32", "int8"],
                                       quality_reference="iris-eval-v1",
                                       quality_max_drift=0.01))
        selected, _ = plan(spec, self.profile)
        self.assertEqual(selected.candidate.precision, "fp32")
        int8 = next(s for s in selected.ranked
                    if s.candidate.precision == "int8")
        self.assertGreater(dict(int8.pressures)["quality"], 1.0)
        self.assertEqual(int8.binding_dimension, "quality")
        self.assertIn("quality_max_drift=0.01", selected.explanation)

    def test_optimize_for_quality_ranks_ties_by_measured_drift(self):
        # Controlled estimates force an exact worst-pressure tie between
        # fp64 and int8; the optimize_for key is then the only decider,
        # and it reads differently per dimension: latency takes the lower
        # latency estimate (int8), quality takes the lower *measured
        # drift* (fp64, exactly zero).
        from unittest import mock
        from aacl.planner import scorer
        from aacl.planner.estimates import CandidateEstimate
        table = {("cpu-python", "fp64"): CandidateEstimate(0.020, 50.0, 0.002),
                 ("cpu-python", "int8"): CandidateEstimate(0.010, 50.0, 0.001)}
        fake = lambda candidate, profile, spec: table[(candidate.backend,
                                                       candidate.precision)]
        candidates = [ExecutionCandidate("cpu-python", "fp64", True, 0),
                      ExecutionCandidate("cpu-python", "int8", True, 2)]
        with mock.patch("aacl.planner.scorer.estimate", side_effect=fake):
            by_latency = scorer.select(
                WorkloadSpec.parse(dict(self.base, memory_limit_mb=100,
                                        optimize_for="latency",
                                        quality_reference="iris-eval-v1")),
                self.profile, candidates)
            by_quality = scorer.select(
                WorkloadSpec.parse(dict(self.base, memory_limit_mb=100,
                                        optimize_for="quality",
                                        quality_reference="iris-eval-v1")),
                self.profile, candidates)
        self.assertEqual(by_latency.chosen.candidate.precision, "int8")
        self.assertEqual(by_quality.chosen.candidate.precision, "fp64")
        self.assertEqual(by_quality.chosen.drift["mean_score_error"], 0.0)

    def test_unmeasured_path_is_demonstrated(self):
        # No reference declared: the plan's exact sentence, no quality
        # pressure anywhere, and no drift carried.
        spec = WorkloadSpec.parse(dict(self.base, latency_target_ms=0.015))
        selected, _ = plan(spec, self.profile)
        self.assertIn("quality unmeasured — no reference", selected.explanation)
        self.assertIsNone(selected.quality_drift)
        for scored in selected.ranked:
            self.assertNotIn("quality", dict(scored.pressures))
            self.assertIsNone(scored.drift)

    def test_reference_and_tolerance_validation(self):
        # An unknown reference name is a typed refusal, not a silent no-op.
        with self.assertRaises(Rejection) as unknown:
            WorkloadSpec.parse(dict(self.base, quality_reference="no-such-set"))
        self.assertEqual(unknown.exception.code, "UNKNOWN_QUALITY_REFERENCE")
        # A real name on the wrong model is refused the same way.
        with self.assertRaises(Rejection):
            WorkloadSpec.parse({"input": [1, 2, 3, 4],
                                "quality_reference": "iris-eval-v1"})
        # A tolerance with nothing to measure against is refused.
        with self.assertRaises(Rejection):
            WorkloadSpec.parse(dict(self.base, quality_max_drift=0.1))
        # And a negative tolerance is not a number the spec will carry.
        with self.assertRaises(Rejection):
            WorkloadSpec.parse(dict(self.base,
                                    quality_reference="iris-eval-v1",
                                    quality_max_drift=-0.1))

    def test_iris_plan_deterministic(self):
        # Same targeted request through the service twice: identical plan,
        # measured drift and ranked fallback order included.
        request = dict(self.base, latency_target_ms=0.015,
                       allowed_precisions=["fp64", "fp32", "int8"],
                       quality_reference="iris-eval-v1", quality_max_drift=0.1)
        self.assertEqual(self.runtime.infer(request)["plan"],
                         self.runtime.infer(request)["plan"])


class Phase5Tests(unittest.TestCase):
    """GPU backend + the leak test (Phase 5): honest discovery, the
    registration seam, routing, per-backend estimates — and the
    properties that must hold on a machine with no GPU at all, which
    is the machine this suite was built on. Three earlier tests were
    adapted to count relative to the registry (reasons recorded at
    each); every other prior test is unmodified. The GPU-present
    tests live in Phase5GPUTests below and skip cleanly where no
    device genuinely exists."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")
        self.request = {"input": [1, 2, 3, 4]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_discovery_registers_the_cpu_and_only_real_backends(self):
        from aacl.backends import discovery
        from aacl.backends.gpu import probe_gpu_profile
        profiles = discovery.registered_profiles()
        names = [p.name for p in profiles]
        # The CPU reference backend is always registered, and first:
        # it is the registry's primary.
        self.assertEqual(names[0], "cpu-python")
        # A GPU profile exists exactly when the probe genuinely found
        # a device — never because the module exists, or torch imports,
        # or a name was hoped for.
        if probe_gpu_profile() is None:
            self.assertEqual(names, ["cpu-python"])
        else:
            self.assertEqual(len(names), 2)
            self.assertTrue(names[1].startswith("gpu-"))
            # The GPU advertises only what its probe executed — and
            # int8 is never among it: no integer artifact runs there.
            self.assertNotIn("int8", profiles[1].precisions)
            self.assertLessEqual(set(profiles[1].precisions), {"fp32", "fp64"})
        # Discovery is one snapshot per process.
        self.assertIs(discovery.registered_backends(),
                      discovery.registered_backends())
        self.assertEqual(discovery.primary_profile(), BackendProfile())

    def test_no_gpu_plans_are_the_phase4_plans(self):
        from aacl.backends.gpu import probe_gpu_profile
        if probe_gpu_profile() is not None:
            self.skipTest("a GPU is present; the no-GPU property does "
                          "not apply on this machine")
        spec = WorkloadSpec.parse(self.request)
        selected, candidates = plan(spec, BackendProfile())
        self.assertEqual({c.backend for c in candidates}, {"cpu-python"})
        direct, _ = plan(spec, CPUBackend().capabilities())
        self.assertEqual(selected, direct)
        # Through the runtime's new default wiring, the same plan and
        # the reference output — Phase 4 behavior, byte for byte.
        result = Runtime(self.path).infer(self.request)
        self.assertEqual(result["plan"]["artifact_id"], direct.artifact_id)
        self.assertEqual(result["plan"]["candidate"]["backend"], "cpu-python")
        self.assertEqual(result["output"], {"score": 4.375, "label": 1})

    def test_router_dispatches_by_the_plans_own_candidate(self):
        from dataclasses import replace

        from aacl.backends.router import BackendRouter
        from aacl.models.registry import (artifact_id, source_digest,
                                          transform_version)
        calls = []

        class StubBackend:
            def capabilities(self):
                return BackendProfile(name="stub-gpu",
                                      precisions=("fp64", "fp32"))

            def submit(self, selected, values):
                calls.append(selected.candidate.backend)
                return CompletedHandle(output={"score": 9.0, "label": 1})

        router = BackendRouter({"cpu-python": CPUBackend(),
                                "stub-gpu": StubBackend()},
                               primary="cpu-python")
        # The router's face to planning is the primary's profile.
        self.assertEqual(router.capabilities(), BackendProfile())
        spec = WorkloadSpec.parse(self.request)
        selected, _ = plan(spec, BackendProfile())
        self.assertEqual(router.submit(selected, spec.input).result(),
                         {"score": 4.375, "label": 1})
        # A plan naming the other backend is delivered to that backend
        # — the router decides nothing, it delivers.
        stub_candidate = ExecutionCandidate("stub-gpu", "fp64", True, 0)
        stub_artifact = artifact_id(spec.model_id, source_digest(spec.model_id),
                                    "fp64", transform_version("fp64"),
                                    {"backend": "stub-gpu"})
        stub_plan = replace(selected, candidate=stub_candidate,
                            artifact_id=stub_artifact)
        self.assertEqual(router.submit(stub_plan, spec.input).result(),
                         {"score": 9.0, "label": 1})
        self.assertEqual(calls, ["stub-gpu"])
        # A candidate naming an unregistered backend is refused in
        # writing, not silently delivered somewhere else.
        unknown = replace(selected, candidate=ExecutionCandidate(
            "no-such-backend", "fp64", True, 0))
        with self.assertRaises(Rejection):
            router.submit(unknown, spec.input).result()

    def test_generate_unions_registered_backends_only(self):
        from unittest import mock

        from aacl.backends import discovery
        from aacl.planner import candidate_generator
        gpu_profile = BackendProfile(name="gpu-rocm",
                                     precisions=("fp32", "fp64"))
        with mock.patch.object(discovery, "registered_profiles",
                               return_value=(BackendProfile(), gpu_profile)):
            candidates = candidate_generator.generate(BackendProfile(),
                                                      "linear-demo-v1")
            by_backend = {}
            for c in candidates:
                by_backend.setdefault(c.backend, set()).add(c.precision)
            # Both backends' float paths — and no int8 for either: the
            # demo model has no transform, and the GPU claims none.
            self.assertEqual(by_backend, {"cpu-python": {"fp64", "fp32"},
                                          "gpu-rocm": {"fp64", "fp32"}})
            # The anchoring rule: a profile naming no registered
            # backend plans against itself alone — the Phase 0 remote
            # test's world, unchanged.
            remote = BackendProfile(name="remote-test", local=False)
            alone = candidate_generator.generate(remote, "linear-demo-v1")
            self.assertEqual({c.backend for c in alone}, {"remote-test"})

    def test_gpu_estimates_are_a_separate_static_row(self):
        from aacl.planner import estimates
        spec = WorkloadSpec.parse(self.request)
        profile = BackendProfile()
        gpu64 = estimates.estimate(ExecutionCandidate("gpu-rocm", "fp64",
                                                      True, 0), profile, spec)
        cpu64 = estimates.estimate(ExecutionCandidate("cpu-python", "fp64",
                                                      True, 0), profile, spec)
        cpu32 = estimates.estimate(ExecutionCandidate("cpu-python", "fp32",
                                                      True, 1), profile, spec)
        # The GPU row's own constants price the GPU candidate — not the
        # CPU's figures wearing a GPU name. (Demo model: 5 parameters,
        # 4 inputs, 1 output at 8 bytes.)
        bytes_moved = (5 + 4 + 1) * 8
        self.assertAlmostEqual(
            gpu64.estimated_latency_ms,
            estimates.GPU_DISPATCH_OVERHEAD_MS
            + bytes_moved * estimates.GPU_PER_BYTE_MS, places=15)
        self.assertNotEqual(gpu64.estimated_latency_ms,
                            cpu64.estimated_latency_ms)
        # The placeholder's shape, stated in the estimator: at this
        # size the launch overhead dominates (GPU fp64 estimates above
        # CPU fp32, below CPU fp64), and the device-context allowance
        # makes its memory estimate honestly larger.
        self.assertLess(cpu32.estimated_latency_ms, gpu64.estimated_latency_ms)
        self.assertLess(gpu64.estimated_latency_ms, cpu64.estimated_latency_ms)
        self.assertGreater(gpu64.estimated_memory_mb, cpu64.estimated_memory_mb)
        # A backend with no row of its own is priced by the reference
        # (CPU) row — the Phase 3 bounded-attempts world depends on it.
        other = estimates.estimate(ExecutionCandidate("backend-0", "fp64",
                                                      True, 0), profile, spec)
        self.assertEqual(other, cpu64)

    def test_gpu_backend_absent_is_none_not_an_error(self):
        from aacl.backends.gpu import GPUBackend, probe_gpu_profile
        if probe_gpu_profile() is not None:
            self.skipTest("a GPU is present on this machine")
        # Absence is a discovery result, reported as None — and a
        # backend for hardware that isn't there refuses to be built,
        # because constructing one would be a claim.
        self.assertIsNone(GPUBackend.discover())
        with self.assertRaises(RuntimeError):
            GPUBackend()


def _gpu_present():
    from aacl.backends.gpu import probe_gpu_profile
    return probe_gpu_profile() is not None


@unittest.skipUnless(_gpu_present(), "no GPU device on this machine")
class Phase5GPUTests(unittest.TestCase):
    """The GPU-present half of Phase 5. These run only where discovery
    genuinely finds a device — the Strix Halo session the runbook
    describes — and skip everywhere else, including the machine this
    phase was built on. Nothing here is faked on a GPU-less machine;
    that is the point of the split."""

    def setUp(self):
        from aacl.backends import discovery
        backends = discovery.registered_backends()
        self.gpu_name = next(n for n in backends if n != "cpu-python")
        self.gpu = backends[self.gpu_name]
        self.cpu = CPUBackend()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _forced(self, spec, backend_name, precision):
        from dataclasses import replace

        from aacl.models.registry import (artifact_id, source_digest,
                                          transform_version)
        base, candidates = plan(spec, CPUBackend().capabilities())
        candidate = next(c for c in candidates
                         if c.backend == backend_name
                         and c.precision == precision)
        artifact = artifact_id(spec.model_id, source_digest(spec.model_id),
                               precision, transform_version(precision),
                               {"backend": backend_name})
        return replace(base, candidate=candidate, artifact_id=artifact)

    def test_gpu_executes_both_models_and_agrees_with_cpu(self):
        cases = [({"input": [1, 2, 3, 4]}, "fp64"),
                 ({"input": [1, 2, 3, 4]}, "fp32"),
                 ({"model_id": "iris-logreg-v1",
                   "input": [5.1, 3.5, 1.4, 0.2]}, "fp64"),
                 ({"model_id": "iris-logreg-v1",
                   "input": [5.1, 3.5, 1.4, 0.2]}, "fp32")]
        for raw, precision in cases:
            with self.subTest(raw=raw, precision=precision):
                spec = WorkloadSpec.parse(raw)
                cpu_out = self.cpu.submit(
                    self._forced(spec, "cpu-python", precision),
                    spec.input).result()
                gpu_out = self.gpu.submit(
                    self._forced(spec, self.gpu_name, precision),
                    spec.input).result()
                # Labels exactly; scores within fp32 tolerance — the
                # CPU's step-by-step rounding is its own discipline,
                # not the device's.
                self.assertEqual(gpu_out["label"], cpu_out["label"])
                # Fixed 2026-11-17, on this test's first-ever run (the
                # Strix, ROCm 7.14.1): dict.get's default is evaluated
                # eagerly, so [out["score"]] raised KeyError for the
                # iris model's scores-shaped output before .get could
                # answer. A bug in the test, not in either backend —
                # the labels above had already agreed. Branch instead.
                cpu_scores = (cpu_out["scores"] if "scores" in cpu_out
                              else [cpu_out["score"]])
                gpu_scores = (gpu_out["scores"] if "scores" in gpu_out
                              else [gpu_out["score"]])
                for got, want in zip(gpu_scores, cpu_scores):
                    self.assertAlmostEqual(got, want, delta=1e-5)

    def test_gpu_refuses_what_it_never_claimed(self):
        from dataclasses import replace
        spec = WorkloadSpec.parse({"input": [1, 2, 3, 4]})
        base, _ = plan(spec, CPUBackend().capabilities())
        int8_plan = replace(base, candidate=ExecutionCandidate(
            self.gpu_name, "int8", True, 2), artifact_id="whatever")
        with self.assertRaises(Rejection):
            self.gpu.submit(int8_plan, spec.input).result()
        # And a plan whose artifact identity is wrong is refused the
        # same way the CPU backend refuses it.
        fp64_plan = self._forced(spec, self.gpu_name, "fp64")
        forged = replace(fp64_plan, artifact_id="wrong")
        with self.assertRaises(Rejection):
            self.gpu.submit(forged, spec.input).result()

    def test_planner_chooses_gpu_and_cpu_for_different_workloads(self):
        runtime = Runtime(self.path)
        # fp64 only, under a latency target the CPU's fp64 estimate
        # breaks and the GPU's does not: the device is chosen.
        tight = runtime.infer({"input": [1, 2, 3, 4],
                               "allowed_precisions": ["fp64"],
                               "latency_target_ms": 0.018})
        self.assertEqual(tight["plan"]["candidate"]["backend"], self.gpu_name)
        self.assertEqual(tight["output"], {"score": 4.375, "label": 1})
        # No targets at all: the standing preference, and its backend
        # tie-break, keep the reference result on the CPU — the default
        # plan is Phase 4's plan, on the reference backend.
        plain = runtime.infer({"input": [1, 2, 3, 4]})
        self.assertEqual(plain["plan"]["candidate"]["backend"], "cpu-python")
        self.assertEqual(plain["output"], {"score": 4.375, "label": 1})


class Phase5ProbeIsolationTests(unittest.TestCase):
    """The subprocess probe (Phase 5 amendment, 2026-11-17): discovery
    must survive a backend whose device runtime crashes natively.

    The Strix Halo session supplied the evidence. The machine's torch
    build segfaulted inside its bundled HSA runtime on the first
    dispatched kernel, and the in-process probe took the whole
    runtime — CPU path included — down with it. These tests stand in
    for that machine with a fake child process: killed by a signal,
    hung past the timeout, answering garbage, answering an impossible
    claim, and answering honestly. Each of the first four is the same
    discovery result — no GPU — and the runtime must serve the CPU
    through all of them. No earlier test is modified."""

    PROFILE = {
        "name": "gpu-rocm",
        "architecture": "AMD Radeon 8060S Graphics",
        "logical_cores": 40,
        "runtime": "2.12.0+rocm7.1",
        "precisions": ["fp64", "fp32"],
        "local": True,
        "total_memory_bytes": 1024,
        "available_memory_bytes": 512,
        "max_cache_bytes": 256,
    }

    def setUp(self):
        import subprocess
        import sys
        from unittest import mock

        from aacl.backends import discovery
        from aacl.backends import gpu
        self.subprocess = subprocess
        self.sys = sys
        self.mock = mock
        self.gpu = gpu
        self.discovery = discovery
        self._saved_cache = gpu._profile_cache
        self._saved_snapshot = discovery._SNAPSHOT
        gpu._profile_cache = gpu._PROFILE_UNSET
        discovery._SNAPSHOT = None
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "events.jsonl")

    def tearDown(self):
        self.gpu._profile_cache = self._saved_cache
        self.discovery._SNAPSHOT = self._saved_snapshot
        self.tmp.cleanup()

    def _child(self, returncode=0, stdout=""):
        """Patch the probe's subprocess call to a fake child with the
        given exit status and output."""
        completed = self.subprocess.CompletedProcess(
            args=["probe"], returncode=returncode,
            stdout=stdout, stderr="")
        patcher = self.mock.patch.object(
            self.gpu.subprocess, "run", return_value=completed)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_child_killed_by_a_signal_means_no_gpu(self):
        # Exit -11 is what the parent sees when the child dies of
        # SIGSEGV inside a broken device runtime — the Strix result.
        self._child(returncode=-11)
        self.assertIsNone(self.gpu.probe_gpu_profile())
        self.assertIsNone(self.gpu.GPUBackend.discover())

    def test_child_hanging_past_the_timeout_means_no_gpu(self):
        patcher = self.mock.patch.object(
            self.gpu.subprocess, "run",
            side_effect=self.subprocess.TimeoutExpired(
                cmd=["probe"], timeout=self.gpu.PROBE_TIMEOUT_SECONDS))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertIsNone(self.gpu.probe_gpu_profile())

    def test_child_answering_garbage_means_no_gpu(self):
        self._child(stdout="the device is fine, trust me\n")
        self.assertIsNone(self.gpu.probe_gpu_profile())

    def test_child_claiming_int8_is_refused(self):
        # A profile is a claim, and the probe's answer is held to the
        # same standard as any other: this backend never advertises
        # int8, so a child saying otherwise is not believed.
        claim = dict(self.PROFILE, precisions=["int8"])
        self._child(stdout=json.dumps(claim) + "\n")
        self.assertIsNone(self.gpu.probe_gpu_profile())

    def test_child_answering_honestly_builds_the_profile(self):
        self._child(stdout=json.dumps(self.PROFILE) + "\n")
        profile = self.gpu.probe_gpu_profile()
        self.assertEqual(profile.name, "gpu-rocm")
        self.assertEqual(profile.precisions, ("fp64", "fp32"))
        self.assertEqual(profile.total_memory_bytes, 1024)
        self.assertEqual(profile.max_cache_bytes, 256)

    def test_the_runtime_serves_the_cpu_through_a_crashing_probe(self):
        # The amendment's whole point, in the Strix's own scenario:
        # discovery's child dies by signal, and a request still gets
        # the CPU reference answer, from a CPU-only registry.
        self._child(returncode=-11)
        self.assertEqual(
            [p.name for p in self.discovery.registered_profiles()],
            ["cpu-python"])
        result = Runtime(self.path).infer({"input": [1, 2, 3, 4]})
        self.assertEqual(result["output"], {"score": 4.375, "label": 1})
        self.assertEqual(result["plan"]["candidate"]["backend"],
                         "cpu-python")

    def test_the_real_child_contract_on_this_machine(self):
        # No fakes: run the child exactly as discovery runs it, and
        # hold the pair to the contract on whichever machine this is.
        # A machine's torch comes in three states — absent, working,
        # and broken — and the first version of this test modeled
        # only two: it asserted the child always exits 0, which
        # failed on the Strix's broken user-site torch (the child
        # died by SIGSEGV, -11) even though the parent absorbed the
        # death exactly as designed. The contract is not "the child
        # always answers"; it is "the parent's belief matches the
        # child's behavior": a clean answer is believed exactly as
        # given, and a dead child means no GPU profile, never an
        # exception.
        try:
            completed = self.subprocess.run(
                [self.sys.executable, "-m", "aacl.backends.gpu"],
                capture_output=True, text=True, timeout=120)
        except self.subprocess.TimeoutExpired:
            completed = None
        profile = self.gpu.probe_gpu_profile()
        if completed is None or completed.returncode != 0:
            self.assertIsNone(profile)
            return
        answer = json.loads(completed.stdout.strip().splitlines()[-1])
        if answer is None:
            self.assertIsNone(profile)
        else:
            self.assertEqual(set(answer), self.gpu._PROBE_KEYS)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.name, answer["name"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
