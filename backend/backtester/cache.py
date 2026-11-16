"""Per-worker caches for batch experiments (D-058) and curve downsampling for experiment pages (D-062).

A worker processes one run at a time, but the children of one experiment usually share a symbol and period, and often
the same indicators. Caching bars and indicator series per process removes that duplicated work while each child stays
its own job (parallel across workers, retried and tracked on its own). Both caches are bounded LRUs; correctness never
depends on them: a miss just recomputes.
"""
import threading
from collections import OrderedDict


class LRU:
    """A bounded least-recently-used map with hit/miss counters. Thread-safe (EMBEDDED_WORKER runs a consumer thread)."""

    def __init__(self, maxsize):
        self.maxsize = maxsize
        self._data = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def get(self, key, default=None):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return default

    def put(self, key, value):
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def __contains__(self, key):
        with self._lock:
            return key in self._data

    def __len__(self):
        return len(self._data)

    def clear(self):
        with self._lock:
            self._data.clear()
            self.hits = self.misses = 0

    def stats(self):
        return {"hits": self.hits, "misses": self.misses, "size": len(self._data)}


# Bars: (symbol, start, end, warm-up bars, coverage fetched_at) -> (warmup, bars, manifest). A re-download changes
# fetched_at, so stale entries are never hit. Indicator series: (data hash, indicator, params) -> {output: [...]}.
BARS = LRU(maxsize=16)
INDICATORS = LRU(maxsize=128)


class IndicatorCache:
    """Adapter for spec.signals: a dict-like view of INDICATORS scoped to one data set (its hash)."""

    def __init__(self, data_key, store=INDICATORS):
        self.data_key, self.store = data_key, store

    def get(self, key):
        return self.store.get((self.data_key, key))

    def put(self, key, value):
        self.store.put((self.data_key, key), value)


def downsample(curve, max_points=500):
    """Reduce [[date, value], ...] to about max_points while keeping its shape: split into buckets and keep each
    bucket's minimum and maximum (in time order), plus the first and last points. Peaks and drawdowns survive,
    which plain every-n-th sampling would lose."""
    n = len(curve)
    if n <= max_points:
        return list(curve)
    buckets = max(1, (max_points - 2) // 2)
    size = (n - 2) / buckets
    out = [curve[0]]
    for b in range(buckets):
        lo, hi = 1 + int(b * size), 1 + int((b + 1) * size)
        chunk = curve[lo:hi]
        if not chunk:
            continue
        i_min = min(range(len(chunk)), key=lambda i: chunk[i][1])
        i_max = max(range(len(chunk)), key=lambda i: chunk[i][1])
        for i in sorted({i_min, i_max}):
            out.append(chunk[i])
    out.append(curve[-1])
    return out
