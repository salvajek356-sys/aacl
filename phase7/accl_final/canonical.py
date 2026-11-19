"""Shared primitives: canonical form, digests, strict JSON loading.

These are the parts the architecture decisions allow to be
shared — schemas, canonicalization rules, and cryptographic
primitives. The arithmetic being verified is never shared;
executor and verifier each implement it separately.

Canonical form (a project-specific v0.1 rule, not RFC 8785
JCS): json.dumps(sort_keys=True, ensure_ascii=True,
separators=(',', ':'), allow_nan=False), encoded as ASCII.
SHA-256, lower-case hex.
"""
import hashlib
import json
from pathlib import Path


class InvalidArtifact(ValueError):
    pass


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest(obj):
    return sha256_bytes(canonical_json(obj))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidArtifact(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise InvalidArtifact(f"invalid JSON constant: {value}")


def load_json(path):
    """Load JSON strictly: duplicate members and NaN/Infinity
    constants are rejected, never silently absorbed."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidArtifact(f"cannot load JSON: {exc}") from exc


def validate_hex_digest(value):
    return (type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


MAX_ARTIFACT_BYTES = 2_000_000


def artifact_hash(path):
    """SHA-256 of a supplied artifact's bytes. Proves identity
    of the bytes provided to verification — not that those
    bytes were loaded or executed."""
    p = Path(path)
    if not p.is_file() or p.is_symlink():
        raise InvalidArtifact("artifact must be an existing regular nonsymlink file")
    if p.stat().st_size > MAX_ARTIFACT_BYTES:
        raise InvalidArtifact("artifact exceeds 2,000,000 bytes")
    with p.open("rb") as handle:
        data = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise InvalidArtifact("artifact exceeds 2,000,000 bytes")
    return sha256_bytes(data)
