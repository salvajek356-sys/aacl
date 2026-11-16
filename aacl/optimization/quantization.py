"""Quantization as a transformation service (roadmap §9).

Phase 0 placeholder: the module boundary exists so the planner never grows
quantization logic of its own. The service itself — calibration ownership,
artifact production, drift validation against the quality reference — is
Phase 4 work and is intentionally not implemented yet.
"""


def quantize(*args, **kwargs):
    raise NotImplementedError("Quantization service arrives in Phase 4")
