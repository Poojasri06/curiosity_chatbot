"""Small in-memory rate limits that protect the free AI quota from one noisy visitor or a bot."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Allows `limit` hits per `window` seconds for each key. `limit` of 0 turns it off."""

    def __init__(self, limit: int, window: float, clock=time.monotonic, max_keys: int = 10_000):
        self.limit, self.window, self._clock, self._max_keys = limit, window, clock, max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """Record a hit. Returns 0 if allowed, otherwise the seconds to wait."""
        if self.limit <= 0:
            return 0.0
        now = self._clock()
        with self._lock:
            if len(self._hits) > self._max_keys:  # drop idle keys so memory stays bounded
                for stale in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window]:
                    del self._hits[stale]
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1.0, self.window - (now - hits[0]))
            hits.append(now)
            return 0.0
