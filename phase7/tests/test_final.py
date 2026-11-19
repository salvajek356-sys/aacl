"""Final-architecture tests: the locked decision table, strict
int32 semantics, and independent hand-computed vectors.

Expected outputs in the vector tests are written literally in
this file, computed by hand — not produced by either the
executor's or the verifier's implementation. Agreement among
three separate writings of the arithmetic is the evidence.
"""
import copy
import tempfile
import unittest
from pathlib import Path

import accl_final
from accl_final.canonical import (InvalidArtifact, artifact_hash, digest,
                                  load_json)
from accl_final.contract import validate_contract
from accl_final.execute import execute, make_receipt
from accl_final.verify import verify

ROOT = Path(accl_final.__file__).resolve().parent.parent
ARTIFACT = Path(accl_final.__file__).resolve().parent / "execute.py"


def make_contract(a, b):
    return {
        "schema": "accl.execution-contract.v0.1",
        "contract_id": "test-vector",
        "operation": "vector_add_int32",
        "inputs": {"a": a, "b": b},
        "requirements": {"output_dtype": "int32", "output_length": len(a),
                         "verification": "exact"},
    }


class FinalArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_json(ROOT / "contracts" / "vector_add_v01.json")
        cls.ca = digest(cls.contract)
        cls.aa = artifact_hash(ARTIFACT)

    def check(self, *, contract=None, receipt=None, artifact=None,
              ca=None, aa=None):
        c = self.contract if contract is None else contract
        r = execute(self.contract, ARTIFACT) if receipt is None else receipt
        return verify(c, r, ARTIFACT if artifact is None else artifact,
                      self.ca if ca is None else ca,
                      self.aa if aa is None else aa)

    # --- the decision table -------------------------------------
    def test_clean_overall_pass_provenance_indeterminate(self):
        r = self.check()
        self.assertEqual(
            (r["contract_binding"], r["computational_verdict"],
             r["artifact_integrity"], r["execution_provenance"],
             r["overall_verdict"]),
            ("PASS", "PASS", "PASS", "INDETERMINATE", "PASS"))

    def test_altered_artifact_computation_still_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ARTIFACT.name
            p.write_bytes(ARTIFACT.read_bytes() + b"\n# altered\n")
            r = self.check(artifact=p)
        self.assertEqual(
            (r["computational_verdict"], r["artifact_integrity"],
             r["overall_verdict"]), ("PASS", "FAIL", "FAIL"))

    def test_altered_output_rehashed(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["output"][0] += 1
        receipt["output_sha256"] = digest(receipt["output"])
        r = self.check(receipt=receipt)
        self.assertEqual(
            (r["computational_verdict"], r["artifact_integrity"],
             r["overall_verdict"]), ("FAIL", "PASS", "FAIL"))

    def test_bad_contract_anchor_gates_everything(self):
        r = self.check(ca="0" * 64)
        self.assertEqual(
            (r["contract_binding"], r["computational_verdict"],
             r["artifact_integrity"], r["overall_verdict"]),
            ("FAIL", "INDETERMINATE", "INDETERMINATE", "FAIL"))

    def test_missing_artifact_anchor_is_indeterminate_and_fails_closed(self):
        r = self.check(aa="")
        self.assertEqual(
            (r["computational_verdict"], r["artifact_integrity"],
             r["overall_verdict"]), ("PASS", "INDETERMINATE", "FAIL"))

    def test_substituted_contract_detected(self):
        other = make_contract([9, 2, 3, 4], [10, 20, 30, 40])
        r = self.check(contract=other,
                       receipt=execute(other, ARTIFACT))
        self.assertEqual(r["contract_binding"], "FAIL")
        self.assertEqual(r["overall_verdict"], "FAIL")

    # --- independent vectors (hand-computed) --------------------
    def test_reference_vector(self):
        self.assertEqual(execute(self.contract, ARTIFACT)["output"],
                         [11, 22, 33, 44])

    def test_hand_computed_mixed_vector(self):
        contract = make_contract(
            [5, -7, 100, -200, 0, 2147483647, -2147483648, 42],
            [-5, 7, -100, 200, 0, -1, 2147483647, -42])
        receipt = execute(contract, ARTIFACT)
        self.assertEqual(receipt["output"],
                         [0, 0, 0, 0, 0, 2147483646, -1, 0])
        r = verify(contract, receipt, ARTIFACT, digest(contract), self.aa)
        self.assertEqual(r["overall_verdict"], "PASS")

    def test_int32_edges_that_do_not_overflow(self):
        contract = make_contract([-2147483648, 2147483647],
                                 [0, -2147483647])
        self.assertEqual(execute(contract, ARTIFACT)["output"],
                         [-2147483648, 0])

    def test_max_length_vector(self):
        contract = make_contract([1] * 4096, [2] * 4096)
        receipt = execute(contract, ARTIFACT)
        self.assertEqual(receipt["output"], [3] * 4096)
        r = verify(contract, receipt, ARTIFACT, digest(contract), self.aa)
        self.assertEqual(r["overall_verdict"], "PASS")

    # --- strict semantics ---------------------------------------
    def test_overflow_contract_rejected(self):
        with self.assertRaises(InvalidArtifact):
            validate_contract(make_contract([2147483647], [1]))
        with self.assertRaises(InvalidArtifact):
            validate_contract(make_contract([-2147483648], [-1]))
        with self.assertRaises(InvalidArtifact):
            execute(make_contract([2147483647], [1]), ARTIFACT)

    def test_overlong_vector_rejected(self):
        with self.assertRaises(InvalidArtifact):
            validate_contract(make_contract([0] * 4097, [0] * 4097))

    def test_boolean_input_rejected(self):
        with self.assertRaises(InvalidArtifact):
            validate_contract(make_contract([True], [1]))

    def test_duplicate_json_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dup.json"
            p.write_text('{"a": 1, "a": 2}', encoding="utf-8")
            with self.assertRaises(InvalidArtifact):
                load_json(p)

    def test_nan_constant_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "nan.json"
            p.write_text('{"a": NaN}', encoding="utf-8")
            with self.assertRaises(InvalidArtifact):
                load_json(p)

    # --- adversarial evidence -----------------------------------
    def test_forged_hardware_claims_change_nothing(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["claims"] = {"execution_backend": "xdna2-npu",
                             "execution_location": "strix-halo",
                             "hardware_attestation": "claimed-valid"}
        r = self.check(receipt=receipt)
        self.assertEqual(r["execution_provenance"], "INDETERMINATE")
        self.assertEqual(r["overall_verdict"], "PASS")

    def test_extra_receipt_field_fails_structure(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["extra"] = "anything"
        r = self.check(receipt=receipt)
        self.assertEqual(
            (r["receipt_structure"], r["computational_verdict"],
             r["overall_verdict"]), ("FAIL", "INDETERMINATE", "FAIL"))

    def test_old_schema_receipt_not_silently_accepted(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["schema"] = "accl.execution-receipt.v0.1"
        r = self.check(receipt=receipt)
        self.assertEqual((r["receipt_structure"], r["overall_verdict"]),
                         ("FAIL", "FAIL"))

    def test_input_binding_tamper_fails_structure(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["input_sha256"] = "0" * 64
        r = self.check(receipt=receipt)
        self.assertEqual(r["receipt_structure"], "FAIL")
        self.assertEqual(r["overall_verdict"], "FAIL")

    def test_artifact_name_tamper(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["artifact"]["name"] = "other.py"
        r = self.check(receipt=receipt)
        self.assertEqual((r["computational_verdict"], r["artifact_integrity"]),
                         ("PASS", "FAIL"))

    def test_receipt_artifact_digest_tamper(self):
        receipt = make_receipt(self.contract, ARTIFACT)
        receipt["artifact"]["sha256"] = "0" * 64
        r = self.check(receipt=receipt)
        self.assertEqual((r["computational_verdict"], r["artifact_integrity"]),
                         ("PASS", "FAIL"))

    def test_missing_artifact_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(artifact=Path(tmp) / ARTIFACT.name)
        self.assertEqual((r["computational_verdict"], r["artifact_integrity"]),
                         ("PASS", "FAIL"))

    def test_boolean_output_fails_computation_only(self):
        receipt = execute(self.contract, ARTIFACT)
        receipt["output"][0] = True
        receipt["output_sha256"] = digest(receipt["output"])
        r = self.check(receipt=receipt)
        self.assertEqual((r["computational_verdict"], r["artifact_integrity"]),
                         ("FAIL", "PASS"))


if __name__ == "__main__":
    unittest.main()
