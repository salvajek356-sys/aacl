"""ArtifactCache (Phase 3, companion §3): content-addressed storage for
artifacts, keyed by the Phase 1 generalized artifact identity, bounded by
the registry's `max_cache_bytes`, with LRU eviction and pinning for
in-flight plans.

The rules:

- `get_or_build` builds an artifact once and serves it from the cache
  afterwards. A cache hit refreshes the entry's place in the LRU order.
- Eviction is least-recently-used first, and stops at the bound: after any
  insertion the cache holds at most `max_bytes` of artifacts.
- A pinned entry is never evicted. The runtime pins a plan's artifacts for
  the duration of its execution, so eviction cannot take an artifact out
  from under an in-flight plan.
- An artifact larger than the whole cache — or one that cannot fit because
  everything evictable is pinned — is built and returned but not retained.
  The cache says so by absence, not by pretending. A `max_bytes` of None
  means the ceiling is unknown, and an unknown ceiling retains nothing.
- The cache is a process-local structure, used from one thread at a time;
  it makes no promise about concurrency.
"""
from collections import OrderedDict


class ArtifactCache:
    def __init__(self, max_bytes):
        self.max_bytes = max_bytes
        self._entries = OrderedDict()  # artifact_id -> [value, size_bytes, pins]
        self._bytes = 0

    @property
    def bytes_used(self):
        return self._bytes

    def __len__(self):
        return len(self._entries)

    def __contains__(self, artifact_id):
        return artifact_id in self._entries

    def get_or_build(self, artifact_id, size_bytes, build):
        """The cached artifact, building and retaining it on a miss.

        `build` is called only on a miss. If the built artifact cannot be
        retained (see the module rules), it is still returned — the caller
        gets its artifact either way; the cache just cannot promise to
        keep it.
        """
        if size_bytes < 0:
            raise ValueError("artifact size must not be negative")
        entry = self._entries.get(artifact_id)
        if entry is not None:
            self._entries.move_to_end(artifact_id)
            return entry[0]
        value = build()
        if self.max_bytes is None or size_bytes > self.max_bytes:
            return value
        self._evict_to_fit(size_bytes)
        if self._bytes + size_bytes > self.max_bytes:
            return value
        self._entries[artifact_id] = [value, size_bytes, 0]
        self._bytes += size_bytes
        return value

    def pin(self, artifact_id):
        """Protect an entry from eviction. Pinning an artifact the cache
        does not hold is a no-op: resolve it with get_or_build first."""
        entry = self._entries.get(artifact_id)
        if entry is not None:
            entry[2] += 1
            self._entries.move_to_end(artifact_id)

    def unpin(self, artifact_id):
        """Release one pin. An unpinned entry is evictable again, in its
        LRU place."""
        entry = self._entries.get(artifact_id)
        if entry is not None and entry[2] > 0:
            entry[2] -= 1

    def is_pinned(self, artifact_id):
        entry = self._entries.get(artifact_id)
        return bool(entry and entry[2] > 0)

    def _evict_to_fit(self, needed_bytes):
        """Evict least-recently-used unpinned entries until the new
        artifact fits or nothing evictable remains."""
        for artifact_id in list(self._entries):
            if self._bytes + needed_bytes <= self.max_bytes:
                break
            _, size, pins = self._entries[artifact_id]
            if pins:
                continue
            del self._entries[artifact_id]
            self._bytes -= size
