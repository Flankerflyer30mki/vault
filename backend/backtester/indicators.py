"""Technical indicators for builder strategies. Pure functions: no Django, no I/O.

Every function takes full price columns and returns lists aligned to them. The value at index i uses bars 0..i only
(never i+1 or later), so evaluating a rule at bar i cannot see the future. Before an indicator has enough bars it
is None, and a condition that touches None is False.

Conventions (documented because implementations disagree):
- EMA is seeded with the SMA of its first `n` values, then uses alpha = 2 / (n + 1).
- RSI and ATR use Wilder smoothing: the same seeding, alpha = 1 / n.
- Bollinger Bands use the population standard deviation (divide by n), like Bollinger's original definition.
- Donchian channels use the n bars BEFORE the current one, so "close > upper" means a breakout above the prior range.
- ROC is a percentage: 100 * (close / close n bars ago - 1).
"""
import math


def sma(xs, n):
    """Sums the raw values, so Decimal prices give exactly the same result as the engine's built-in sma_N."""
    out = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        out[i] = float(sum(xs[i - n + 1:i + 1]) / n)
    return out


def ema(xs, n, alpha=None):
    """xs may start with None (for example the MACD line); smoothing starts at the first real value."""
    a = 2 / (n + 1) if alpha is None else alpha
    out = [None] * len(xs)
    start = next((i for i, x in enumerate(xs) if x is not None), None)
    if start is None or start + n > len(xs):
        return out
    seed = start + n - 1
    prev = math.fsum(float(x) for x in xs[start:seed + 1]) / n
    out[seed] = prev
    for i in range(seed + 1, len(xs)):
        prev = a * float(xs[i]) + (1 - a) * prev
        out[i] = prev
    return out


def rsi(close, n):
    gains, losses = [None], [None]
    for i in range(1, len(close)):
        d = float(close[i]) - float(close[i - 1])
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain, avg_loss = ema(gains, n, 1 / n), ema(losses, n, 1 / n)
    out = [None] * len(close)
    for i, (g, lo) in enumerate(zip(avg_gain, avg_loss)):
        if g is None:
            continue
        if lo == 0:
            out[i] = 50.0 if g == 0 else 100.0  # flat prices: neutral; only gains: maximum strength
        else:
            out[i] = 100 - 100 / (1 + g / lo)
    return out


def macd(close, fast, slow, signal):
    f, s = ema(close, fast), ema(close, slow)
    line = [None if a is None or b is None else a - b for a, b in zip(f, s)]
    sig = ema(line, signal)
    hist = [None if a is None or b is None else a - b for a, b in zip(line, sig)]
    return {"line": line, "signal": sig, "hist": hist}


def bbands(close, n, k):
    mid = sma(close, n)
    upper, lower = [None] * len(close), [None] * len(close)
    for i in range(n - 1, len(close)):
        window = [float(x) for x in close[i - n + 1:i + 1]]
        m = math.fsum(window) / n
        sd = math.sqrt(math.fsum((x - m) ** 2 for x in window) / n)
        upper[i], lower[i] = mid[i] + k * sd, mid[i] - k * sd
    return {"upper": upper, "middle": mid, "lower": lower}


def atr(high, low, close, n):
    tr = [None]
    for i in range(1, len(close)):
        h, lo, pc = float(high[i]), float(low[i]), float(close[i - 1])
        tr.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return ema(tr, n, 1 / n)


def donchian(high, low, n):
    upper, lower = [None] * len(high), [None] * len(high)
    for i in range(n, len(high)):
        upper[i] = float(max(high[i - n:i]))
        lower[i] = float(min(low[i - n:i]))
    return {"upper": upper, "lower": lower}


def roc(close, n):
    out = [None] * len(close)
    for i in range(n, len(close)):
        base = float(close[i - n])
        if base != 0:
            out[i] = 100 * (float(close[i]) / base - 1)
    return out


# Registry: the only indicators a spec may name. Each entry lists its parameters as
# (name, type, min, max, default), its outputs (the first is the default) and how to compute it.
# lookback(params) = bars needed before the first decision: enough for the value to exist one bar earlier
# (so a crossover can fire on the first bar) plus, for smoothed indicators, 2n more bars to let the seed fade.
REGISTRY = {
    "sma": {"label": "Simple moving average", "params": [("period", int, 2, 200, 20)], "outputs": ["value"],
            "fn": lambda c, p: {"value": sma(c["close"], p["period"])},
            "lookback": lambda p: p["period"]},
    "ema": {"label": "Exponential moving average", "params": [("period", int, 2, 200, 20)], "outputs": ["value"],
            "fn": lambda c, p: {"value": ema(c["close"], p["period"])},
            "lookback": lambda p: 3 * p["period"]},
    "rsi": {"label": "Relative strength index (Wilder)", "params": [("period", int, 2, 200, 14)], "outputs": ["value"],
            "fn": lambda c, p: {"value": rsi(c["close"], p["period"])},
            "lookback": lambda p: 3 * p["period"] + 1},
    "macd": {"label": "MACD", "params": [("fast", int, 2, 100, 12), ("slow", int, 3, 200, 26), ("signal", int, 2, 50, 9)],
             "outputs": ["line", "signal", "hist"],
             "fn": lambda c, p: macd(c["close"], p["fast"], p["slow"], p["signal"]),
             "lookback": lambda p: 3 * (p["slow"] + p["signal"])},
    "bbands": {"label": "Bollinger Bands", "params": [("period", int, 2, 200, 20), ("std", float, 0.5, 5.0, 2.0)],
               "outputs": ["upper", "middle", "lower"],
               "fn": lambda c, p: bbands(c["close"], p["period"], p["std"]),
               "lookback": lambda p: p["period"]},
    "atr": {"label": "Average true range (Wilder)", "params": [("period", int, 2, 200, 14)], "outputs": ["value"],
            "fn": lambda c, p: {"value": atr(c["high"], c["low"], c["close"], p["period"])},
            "lookback": lambda p: 3 * p["period"] + 1},
    "donchian": {"label": "Donchian channel (prior n bars)", "params": [("period", int, 2, 200, 20)],
                 "outputs": ["upper", "lower"],
                 "fn": lambda c, p: donchian(c["high"], c["low"], p["period"]),
                 "lookback": lambda p: p["period"] + 1},
    "roc": {"label": "Rate of change (%)", "params": [("period", int, 1, 200, 10)], "outputs": ["value"],
            "fn": lambda c, p: {"value": roc(c["close"], p["period"])},
            "lookback": lambda p: p["period"] + 1},
}
