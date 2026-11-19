"""Execution Contract v0.1 — strict validation.

A contract is fixed before any execution it governs; its
SHA-256 digest is the binding reference, supplied to the
verifier through a channel independent of the evidence.

Semantics are strict signed-int32: if adding two inputs would
exceed the signed 32-bit range, the contract is invalid and is
rejected before execution. There is no wraparound. A contract
defines one unambiguous mathematical result for every
permitted input.

This module deliberately contains no implementation of the
operation itself. The executor and the verifier each implement
the arithmetic separately (Architecture Decision 1,
2026-11-18); a shared implementation would be a shared
correctness dependency.
"""
from .canonical import InvalidArtifact

SCHEMA = "accl.execution-contract.v0.1"
MIN_I32 = -(2 ** 31)
MAX_I32 = 2 ** 31 - 1
MAX_VECTOR_LENGTH = 4096


def _keys(obj, expected, label):
    if type(obj) is not dict or set(obj) != set(expected):
        raise InvalidArtifact(f"{label}: expected exactly {sorted(expected)}")


def validate_contract(contract):
    _keys(contract, ("schema", "contract_id", "operation", "inputs",
                     "requirements"), "contract")
    if contract["schema"] != SCHEMA:
        raise InvalidArtifact("unsupported contract schema")
    cid = contract["contract_id"]
    if (type(cid) is not str or not 1 <= len(cid) <= 128
            or not all(c.isascii() and (c.isalnum() or c in "-_.") for c in cid)):
        raise InvalidArtifact("invalid contract_id")
    if contract["operation"] != "vector_add_int32":
        raise InvalidArtifact("unsupported operation")
    inputs = contract["inputs"]
    _keys(inputs, ("a", "b"), "inputs")
    a, b = inputs["a"], inputs["b"]
    if (type(a) is not list or type(b) is not list
            or not 1 <= len(a) <= MAX_VECTOR_LENGTH or len(a) != len(b)):
        raise InvalidArtifact("input vectors must have equal length 1..4096")
    for vec in (a, b):
        for x in vec:
            if type(x) is not int or not MIN_I32 <= x <= MAX_I32:
                raise InvalidArtifact(
                    "all inputs must be signed int32 integers (not bool)")
    requirements = contract["requirements"]
    _keys(requirements, ("output_dtype", "output_length", "verification"),
          "requirements")
    if requirements["output_dtype"] != "int32" or requirements["verification"] != "exact":
        raise InvalidArtifact("only exact int32 verification supported")
    if type(requirements["output_length"]) is not int \
            or requirements["output_length"] != len(a):
        raise InvalidArtifact("required output length must equal input length")
    if any(not MIN_I32 <= x + y <= MAX_I32 for x, y in zip(a, b)):
        raise InvalidArtifact("int32 overflow is not supported")
    return contract
