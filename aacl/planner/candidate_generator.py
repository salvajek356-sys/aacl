"""Candidate generation: the feasible search space, before any filtering or
scoring. Phase 0 generates the proof's two CPU precision paths.

Phase 4: generation is model-aware. The floating-point paths are as they
were; an int8 candidate is added when the backend offers int8 *and* the
transformation service has a transform for the model — an int8 artifact
exists only where the service holds calibration data for that model, so
the demo model (which has none) generates exactly the candidates it
always did.

Phase 5: generation is registry-aware, under one anchoring rule. The
passed profile's own paths are generated exactly as before. When the
passed profile names a backend *registered on this machine* (see
backends/discovery.py), every other registered backend's paths join the
search space too — planning for a machine means planning against
everything the machine genuinely has. A profile that names no registered
backend (a test double, a hypothetical remote, a what-if) plans against
itself alone, exactly as it always did. Filtering, scoring, and ranking
are untouched by this: generation enumerates, it does not judge.
"""
from ..optimization import quantization


def _for_profile(profile, model_id):
    from ..core.execution import ExecutionCandidate

    candidates = [ExecutionCandidate(profile.name, p, profile.local, rank)
                  for rank, p in enumerate(("fp64", "fp32")) if p in profile.precisions]
    if (model_id is not None and "int8" in profile.precisions
            and quantization.has_transform(model_id)):
        rank = max((c.preference_rank for c in candidates), default=-1) + 1
        candidates.append(ExecutionCandidate(profile.name, "int8", profile.local,
                                             rank))
    return candidates


def generate(profile, model_id=None):
    candidates = _for_profile(profile, model_id)
    from ..backends import discovery
    profiles = discovery.registered_profiles()
    if any(p.name == profile.name for p in profiles):
        for other in profiles:
            if other.name != profile.name:
                candidates.extend(_for_profile(other, model_id))
    return candidates
