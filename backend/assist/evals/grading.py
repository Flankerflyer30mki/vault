"""Behavioural grading (D-082). The same strategy can be written many ways (">" vs "crosses_above" for an entry that
only matters once, MACD line over signal vs histogram over zero, the 20-day SMA vs the Bollinger middle band), so specs are
compared by what they DO on fixed price series, never by their JSON.

"full" grading compares positions bar by bar (in the market or not: what the engine would hold), which is what the user
cares about; a BUY while already holding changes nothing, so raw signals would be too strict. "entry" grading compares
only when the entry rule fires, for vague prompts where the AI has to choose an exit.
"""
import copy
import math
import random
from functools import lru_cache

from backtester import spec

# Never true: close is never negative. Replaces the exit group for entry-only grading.
NEVER = {"left": {"price": "close"}, "op": "<", "right": {"const": -1}}
BARS = 500


def _series(seed, drift, vol, shape):
    rng = random.Random(seed)
    price, bars = 100.0, []
    for i in range(BARS):
        if shape == "range":
            target = 100 * (1 + 0.09 * math.sin(2 * math.pi * i / 45))
            price += (target - price) * 0.25
        elif shape == "crash":
            drift = 0.0012 if i < 220 else (-0.018 if i < 250 else 0.0015)
        prev = price
        price = max(1.0, price * (1 + drift + rng.gauss(0, vol)))
        o = prev * (1 + rng.gauss(0, vol / 3))
        hi = max(o, price) * (1 + abs(rng.gauss(0, vol / 2)))
        lo = min(o, price) * (1 - abs(rng.gauss(0, vol / 2)))
        volume = int(rng.uniform(2e5, 2e6) * (3 if rng.random() < 0.05 else 1))
        bars.append({"open": o, "high": hi, "low": lo, "close": price, "volume": volume})
    return bars


@lru_cache(maxsize=1)
def series():
    """Five fixed 500-bar series with different characters, so a rule that only fires in one regime still gets tested."""
    return (
        _series(1, 0.0008, 0.012, "trend"),       # steady uptrend
        _series(2, -0.0006, 0.013, "trend"),      # downtrend
        _series(3, 0.0, 0.008, "range"),          # oscillating range: RSI and band extremes
        _series(4, 0.0, 0.015, "crash"),          # rally, crash, recovery
        _series(5, 0.0, 0.018, "trend"),          # volatile random walk
    )


def positions(sigs):
    pos, out = 0, []
    for s in sigs:
        if s == "BUY" and pos == 0:
            pos = 1
        elif s == "SELL" and pos == 1:
            pos = 0
        out.append(pos)
    return out


def entry_only(s):
    out = copy.deepcopy(s)
    out["exit"] = {"any": [NEVER]}
    return out


def behaviour(s, grade="full"):
    """Per series: positions ("full") or entry firings ("entry")."""
    s = spec.validate(s)
    if grade == "entry":
        return [tuple(x == "BUY" for x in spec.signals(entry_only(s), bars)) for bars in series()]
    return [tuple(positions(spec.signals(s, bars))) for bars in series()]


def agreement(a, b):
    same = total = 0
    for x, y in zip(a, b):
        same += sum(p == q for p, q in zip(x, y))
        total += len(x)
    return same / total if total else 0.0


def match(candidate, refs, grade="full"):
    """(matches any reference exactly, best bar-by-bar agreement 0..1)."""
    got = behaviour(candidate, grade)
    best = 0.0
    for ref in refs:
        want = behaviour(ref, grade)
        if got == want:
            return True, 1.0
        best = max(best, agreement(got, want))
    return False, best


def trades(s, grade="full"):
    """(entries, exits) summed over the series: used to check every reference actually trades, so an answer can't pass
    by matching a strategy that never does anything."""
    beh = behaviour(s, grade)
    if grade == "entry":
        return sum(sum(x) for x in beh), 0
    entries = sum(sum(1 for i in range(1, len(p)) if p[i] and not p[i - 1]) + p[0] for p in beh)
    exits = sum(sum(1 for i in range(1, len(p)) if p[i - 1] and not p[i]) for p in beh)
    return entries, exits
