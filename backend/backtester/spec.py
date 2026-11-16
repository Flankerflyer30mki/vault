"""Builder strategies: a versioned JSON spec, validated against an allowlist and interpreted. Never executed as code.

    {"version": 1,
     "entry": {"all": [{"left": {"ind": "ema", "params": {"period": 12}}, "op": "crosses_above",
                        "right": {"ind": "ema", "params": {"period": 26}}}]},
     "exit":  {"any": [{"left": {"ind": "rsi", "params": {"period": 14}}, "op": ">", "right": {"const": 70}}]}}

Signals: on each bar, SELL if the exit group is true, otherwise BUY if the entry group is true, otherwise HOLD. The
long-only engine ignores a BUY while holding and a SELL while flat, so this needs no position state. When entry and
exit are both true, exit wins and a flat strategy stays out (conflicting signals; same spirit as "stop wins").
"""
import copy
import hashlib
import json
import math
import re

from backtester.indicators import REGISTRY

VERSION = 1
MAX_CONDITIONS = 10
MAX_SPEC_BYTES = 8192
MAX_WARMUP_BARS = 600
MAX_CONST = 1e9
PRICE_FIELDS = ("open", "high", "low", "close", "volume")
OPS = {">": "is above", "<": "is below", ">=": "is at or above", "<=": "is at or below",
       "crosses_above": "crosses above", "crosses_below": "crosses below"}


class SpecError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors  # {"entry.all[0].left.params.period": "must be between 2 and 200"}


# ---------------------------------------------------------------- validation

def validate(raw):
    """Returns the normalised spec (defaults filled in) or raises SpecError with every problem found, keyed by path."""
    errors = {}
    try:
        size = len(json.dumps(raw))
    except (TypeError, ValueError):
        raise SpecError({"spec": "must be JSON"}) from None
    if size > MAX_SPEC_BYTES:
        raise SpecError({"spec": f"is too large ({size} bytes, limit {MAX_SPEC_BYTES})"})
    if not isinstance(raw, dict):
        raise SpecError({"spec": "must be an object"})
    _unknown_keys(raw, {"version", "entry", "exit"}, "", errors)
    if raw.get("version") != VERSION or isinstance(raw.get("version"), bool):
        errors["version"] = f"must be {VERSION}"
    out = {"version": VERSION}
    for side in ("entry", "exit"):
        out[side] = _group(raw.get(side), side, errors)
    if errors:
        raise SpecError(errors)
    return out


def _unknown_keys(obj, allowed, path, errors):
    for k in obj:
        if k not in allowed:
            errors[f"{path}.{k}" if path else str(k)] = "unknown field"


def _group(g, path, errors):
    if not isinstance(g, dict) or len(g) != 1 or next(iter(g)) not in ("all", "any"):
        errors[path] = 'must be {"all": [...]} or {"any": [...]}'
        return None
    mode, conds = next(iter(g.items()))
    p = f"{path}.{mode}"
    if not isinstance(conds, list) or not 1 <= len(conds) <= MAX_CONDITIONS:
        errors[p] = f"must be a list of 1 to {MAX_CONDITIONS} conditions"
        return None
    return {mode: [_condition(c, f"{p}[{i}]", errors) for i, c in enumerate(conds)]}


def _condition(c, path, errors):
    if not isinstance(c, dict):
        errors[path] = "must be an object"
        return None
    _unknown_keys(c, {"left", "op", "right"}, path, errors)
    if c.get("op") not in OPS:
        errors[f"{path}.op"] = f"must be one of {', '.join(OPS)}"
    left, right = _operand(c.get("left"), f"{path}.left", errors), _operand(c.get("right"), f"{path}.right", errors)
    if left and right and "const" in left and "const" in right:
        errors[path] = "compare the market to something: both sides can't be numbers"
    return {"left": left, "op": c.get("op"), "right": right}


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _operand(o, path, errors):
    if not isinstance(o, dict):
        errors[path] = "must be an object"
        return None
    kinds = [k for k in ("ind", "price", "const") if k in o]
    if len(kinds) != 1:
        errors[path] = 'must have exactly one of "ind", "price" or "const"'
        return None
    kind = kinds[0]
    if kind == "const":
        _unknown_keys(o, {"const"}, path, errors)
        v = o["const"]
        if not _number(v) or abs(v) > MAX_CONST:
            errors[f"{path}.const"] = f"must be a number between {-MAX_CONST:g} and {MAX_CONST:g}"
            return None
        return {"const": v}
    if kind == "price":
        _unknown_keys(o, {"price"}, path, errors)
        if o["price"] not in PRICE_FIELDS:
            errors[f"{path}.price"] = f"must be one of {', '.join(PRICE_FIELDS)}"
            return None
        return {"price": o["price"]}

    _unknown_keys(o, {"ind", "params", "output"}, path, errors)
    name = o["ind"]
    if not isinstance(name, str) or name not in REGISTRY:
        errors[f"{path}.ind"] = f"must be one of {', '.join(REGISTRY)}"
        return None
    meta = REGISTRY[name]
    raw_params = o.get("params", {})
    if not isinstance(raw_params, dict):
        errors[f"{path}.params"] = "must be an object"
        return None
    _unknown_keys(raw_params, {p[0] for p in meta["params"]}, f"{path}.params", errors)
    params = {}
    for pname, ptype, lo, hi, default in meta["params"]:
        v = raw_params.get(pname, default)
        ok = _number(v) and (ptype is float or float(v).is_integer())
        if not ok or not lo <= v <= hi:
            kind_word = "a whole number" if ptype is int else "a number"
            errors[f"{path}.params.{pname}"] = f"must be {kind_word} between {lo} and {hi}"
            continue
        params[pname] = ptype(v)
    if name == "macd" and "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
        errors[f"{path}.params.slow"] = "must be greater than fast"
    output = o.get("output", meta["outputs"][0])
    if output not in meta["outputs"]:
        errors[f"{path}.output"] = f"must be one of {', '.join(meta['outputs'])}"
    return {"ind": name, "params": params, "output": output}


# ---------------------------------------------------------------- identity and warm-up

def canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


def spec_hash(spec):
    """Same strategy, same hash, whatever the key order. Stored on every run for reproducibility."""
    return hashlib.sha256(canonical(spec).encode()).hexdigest()


def _operands(spec):
    for side in ("entry", "exit"):
        for c in next(iter(spec[side].values())):
            yield c["left"]
            yield c["right"]


def warmup_bars(spec):
    """Bars to load before the start date. At least 1, so a crossover can fire on the first bar."""
    need = [REGISTRY[o["ind"]]["lookback"](o["params"]) for o in _operands(spec) if "ind" in o]
    return min(max([1, *need]), MAX_WARMUP_BARS)


# ---------------------------------------------------------------- interpretation

def signals(spec, bars, cache=None):
    """bars: chronological dicts with open/high/low/close/volume. Returns 'BUY'/'SELL'/'HOLD' per bar.
    Each distinct (indicator, params) is computed once over the whole series. `cache` (optional, with get/put) shares
    those series across runs on the same bars; the caller scopes it to the data set (see cache.IndicatorCache)."""
    cols = {f: [b[f] for b in bars] for f in PRICE_FIELDS}
    floats = {f: [float(x) for x in v] for f, v in cols.items()}
    local = {}

    def series(o):
        if "const" in o:
            return None
        if "price" in o:
            return floats[o["price"]]
        key = (o["ind"], tuple(sorted(o["params"].items())))
        if key not in local:
            computed = cache.get(key) if cache is not None else None
            if computed is None:
                computed = REGISTRY[o["ind"]]["fn"](cols, o["params"])
                if cache is not None:
                    cache.put(key, computed)
            local[key] = computed
        return local[key][o["output"]]

    def truth(c):
        a, b = series(c["left"]), series(c["right"])
        ca, cb = c["left"].get("const"), c["right"].get("const")
        at = (lambda i: a[i]) if a is not None else (lambda i: ca)
        bt = (lambda i: b[i]) if b is not None else (lambda i: cb)
        op = c["op"]
        out = [False] * len(bars)
        for i in range(len(bars)):
            x, y = at(i), bt(i)
            if x is None or y is None:
                continue
            if op in (">", "<", ">=", "<="):
                out[i] = x > y if op == ">" else x < y if op == "<" else x >= y if op == ">=" else x <= y
            elif i > 0:
                px, py = at(i - 1), bt(i - 1)
                if px is None or py is None:
                    continue
                out[i] = (px <= py and x > y) if op == "crosses_above" else (px >= py and x < y)
        return out

    def group(g):
        mode, conds = next(iter(g.items()))
        rows = [truth(c) for c in conds]
        combine = all if mode == "all" else any
        return [combine(r[i] for r in rows) for i in range(len(bars))]

    entry, exit_ = group(spec["entry"]), group(spec["exit"])
    return ["SELL" if x else "BUY" if e else "HOLD" for e, x in zip(entry, exit_)]


def compile_decide(spec, bars, cache=None):
    """A decide(bar, indicators) function for engine.simulate, backed by precomputed signals."""
    by_ts = {b["ts"]: d for b, d in zip(bars, signals(spec, bars, cache))}
    return lambda bar, _indicators: by_ts[bar["ts"]]


# ---------------------------------------------------------------- parameter search (Phase 3)

_PATH = re.compile(r"^(entry|exit)\.(all|any)\[(\d+)\]\.(left|right)\.params\.([a-z_]+)$")


def _label(o, name):
    meta = REGISTRY[o["ind"]]
    args = ", ".join(_num(o["params"][p[0]]) for p in meta["params"])
    return f"{o['ind']}({args}).{name}"


def tunable_params(spec):
    """The numeric parameters a search can vary, grouped by indicator instance: EMA(12) used in both the entry and the
    exit rule is one group with two paths, so a search changes them together (entry on EMA 10 with exit on EMA 12 would
    be a different, accidental strategy). Returns [{label, indicator, name, type, min, max, value, paths}]."""
    groups = {}
    for side in ("entry", "exit"):
        mode, conds = next(iter(spec[side].items()))
        for i, c in enumerate(conds):
            for lr in ("left", "right"):
                o = c[lr]
                if "ind" not in o:
                    continue
                for name, ptype, lo, hi, _default in REGISTRY[o["ind"]]["params"]:
                    key = (o["ind"], tuple(sorted(o["params"].items())), name)
                    g = groups.setdefault(key, {
                        "label": _label(o, name), "indicator": o["ind"], "name": name, "type": ptype.__name__,
                        "min": lo, "max": hi, "value": o["params"][name], "paths": []})
                    g["paths"].append(f"{side}.{mode}[{i}].{lr}.params.{name}")
    return list(groups.values())


def with_params(spec, assignments):
    """A copy of `spec` with each (paths, value) applied. Raises KeyError for a path that isn't a parameter of an
    indicator in this spec. The result is NOT validated; call validate() on it."""
    out = copy.deepcopy(spec)
    for paths, value in assignments:
        for path in paths:
            m = _PATH.match(path)
            if not m:
                raise KeyError(path)
            side, mode, i, lr, name = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5)
            conds = out[side].get(mode)
            if conds is None or i >= len(conds) or "ind" not in conds[i][lr] or name not in conds[i][lr]["params"]:
                raise KeyError(path)
            conds[i][lr]["params"][name] = value
    return out


# ---------------------------------------------------------------- read-only rendering

def _num(v):
    return repr(int(v)) if isinstance(v, float) and v.is_integer() and abs(v) < 1e15 else repr(v)


def _operand_text(o):
    if "const" in o:
        return _num(o["const"])
    if "price" in o:
        return f"bar.{o['price']}"
    meta = REGISTRY[o["ind"]]
    args = ", ".join(_num(o["params"][p[0]]) for p in meta["params"])
    tail = f".{o['output']}" if len(meta["outputs"]) > 1 else ""
    return f"ind.{o['ind']}({args}){tail}"


def _condition_text(c):
    a, b = _operand_text(c["left"]), _operand_text(c["right"])
    if c["op"] in ("crosses_above", "crosses_below"):
        return f"{c['op']}({a}, {b})"
    return f"{a} {c['op']} {b}"


def render_python(spec):
    """Python-shaped text for people to read. Every token comes from the allowlist or a validated number, so the
    text can't carry anything a user typed. Vault never executes it."""
    lines = ["# Builder strategy (spec v1) shown as Python for reading.",
             "# Vault interprets the JSON spec; this text is never executed.",
             "def on_bar(bar, ind):"]
    for side in ("entry", "exit"):
        mode, conds = next(iter(spec[side].items()))
        lines.append(f"    {side} = {mode}([")
        lines += [f"        {_condition_text(c)}," for c in conds]
        lines.append("    ])")
    lines += ["    if exit:  # exit wins when both are true", '        return "SELL"', "    if entry:",
              '        return "BUY"', '    return "HOLD"']
    return "\n".join(lines) + "\n"


def catalog():
    """Everything the builder form needs, so the UI never hard-codes the allowlist."""
    return {
        "version": VERSION,
        "max_conditions": MAX_CONDITIONS,
        "operators": [{"id": k, "label": v} for k, v in OPS.items()],
        "price_fields": list(PRICE_FIELDS),
        "indicators": [{"id": k, "label": m["label"], "outputs": m["outputs"],
                        "params": [{"name": n, "type": t.__name__, "min": lo, "max": hi, "default": d}
                                   for n, t, lo, hi, d in m["params"]]}
                       for k, m in REGISTRY.items()],
    }
