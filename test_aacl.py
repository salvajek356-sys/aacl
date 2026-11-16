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


if __name__ == "__main__":
    unittest.main(verbosity=2)
