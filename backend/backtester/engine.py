"""Deterministic backtest simulation. No Django, no I/O: bars in, ledger out.

Execution model (documented in README "Execution model"):
- The strategy sees bar t (OHLC, close included) and indicators computed through bar t.
- Its decision becomes an order that fills at the OPEN of bar t+1. A decision on the
  last bar never fills. This removes same-bar lookahead.
- Stop-loss / take-profit are evaluated against each bar's OHLC while a position is open:
  a gap through the level fills at the open; an intrabar touch fills at the level;
  if one bar touches both, the stop is assumed to fill first (conservative).
- Long-only, one position at a time, fractional shares rounded down to QTY_STEP.
- Commission and slippage are charged exactly once per fill; position sizing includes
  the commission so cash never goes negative.
- Equity at every bar = cash + quantity * close. The open position is NOT force-closed
  at the end; final value is the last equity point (marked to market).
"""
import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

ENGINE_VERSION = "2.0.0"
QTY_STEP = Decimal("0.000001")
CENT = Decimal("0.0001")
SMA_WINDOWS = (10, 50)
WARMUP_BARS = max(SMA_WINDOWS)


class StrategyError(Exception):
    """The strategy itself failed (exception, bad output, timeout). Not retryable."""


@dataclass(frozen=True)
class Params:
    starting_cash: Decimal
    max_position_pct: Decimal = Decimal("1")
    commission_pct: Decimal = Decimal("0.001")
    slippage_pct: Decimal = Decimal("0.0005")
    stop_loss_pct: Decimal | None = None
    take_profit_pct: Decimal | None = None


@dataclass
class Fill:
    side: str
    ts: object
    price: Decimal  # executed price, slippage included
    quantity: Decimal
    commission: Decimal
    slippage_cost: Decimal
    cash_after: Decimal
    reason: str  # signal | stop_loss | take_profit


@dataclass
class Result:
    fills: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)  # [(ts, Decimal equity)]
    cash: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")


def simulate(bars, decide, p, warmup=0, on_progress=None):
    """bars: chronological dicts with ts/open/high/low/close as Decimal.
    The first `warmup` bars only feed indicators; the strategy never sees them.
    decide(bar_dict, indicators) -> 'BUY' | 'SELL' | 'HOLD'."""
    r = Result(cash=p.starting_cash)
    closes = []
    entry = None
    pending = None
    one = Decimal("1")

    def fill(side, bar, raw_price, reason):
        nonlocal entry
        if side == "BUY":
            price = raw_price * (one + p.slippage_pct)
            budget = r.cash * p.max_position_pct
            qty = (budget / (price * (one + p.commission_pct))).quantize(QTY_STEP, ROUND_DOWN)
            if qty <= 0:
                return
            gross = qty * price
            fee = gross * p.commission_pct
            r.cash -= gross + fee
            r.quantity = qty
            entry = price
        else:
            price = raw_price * (one - p.slippage_pct)
            qty = r.quantity
            gross = qty * price
            fee = gross * p.commission_pct
            r.cash += gross - fee
            r.quantity = Decimal("0")
            entry = None
        r.fills.append(Fill(side, bar["ts"], price, qty, fee, abs(price - raw_price) * qty, r.cash, reason))

    for i, bar in enumerate(bars):
        closes.append(bar["close"])
        if i < warmup:
            continue

        if pending:
            fill(pending, bar, bar["open"], "signal")
            pending = None

        if r.quantity > 0:
            stop = entry * (one - p.stop_loss_pct) if p.stop_loss_pct else None
            target = entry * (one + p.take_profit_pct) if p.take_profit_pct else None
            if stop is not None and bar["open"] <= stop:
                fill("SELL", bar, bar["open"], "stop_loss")
            elif target is not None and bar["open"] >= target:
                fill("SELL", bar, bar["open"], "take_profit")
            elif stop is not None and bar["low"] <= stop:
                fill("SELL", bar, stop, "stop_loss")
            elif target is not None and bar["high"] >= target:
                fill("SELL", bar, target, "take_profit")

        equity = r.cash + r.quantity * bar["close"]
        r.equity_curve.append((bar["ts"], equity))

        indicators = {f"sma_{w}": _sma(closes, w) for w in SMA_WINDOWS}
        decision = decide(bar, indicators)
        if decision == "BUY" and r.quantity == 0:
            pending = "BUY"
        elif decision == "SELL" and r.quantity > 0:
            pending = "SELL"

        if on_progress:
            on_progress(i + 1 - warmup)
    return r


def _sma(closes, window):
    if len(closes) < window:
        return None
    return float(sum(closes[-window:]) / window)


def metrics(result, p, bars):
    """All metrics derive from the ledger's equity curve. Ratios are floats; None = undefined."""
    curve = [float(v) for _, v in result.equity_curve]
    out = {
        "final_value": result.equity_curve[-1][1].quantize(CENT) if curve else None,
        "cagr": None, "sharpe_ratio": None, "max_drawdown": None, "win_rate": None,
        "buy_and_hold_return": None,
        "total_commission": sum((f.commission for f in result.fills), Decimal("0")).quantize(CENT),
        "total_slippage": sum((f.slippage_cost for f in result.fills), Decimal("0")).quantize(CENT),
    }
    if not curve:
        return out

    start, end = float(p.starting_cash), curve[-1]
    years = (result.equity_curve[-1][0] - result.equity_curve[0][0]).days / 365.25
    if years > 0 and start > 0 and end > 0:
        out["cagr"] = (end / start) ** (1 / years) - 1

    peak, max_dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    out["max_drawdown"] = max_dd

    # Sharpe: daily equity returns, risk-free rate 0, annualised with sqrt(252).
    rets = [(b - a) / a for a, b in zip(curve, curve[1:]) if a > 0]
    if len(rets) > 1:
        mean = sum(rets) / len(rets)
        std = math.sqrt(sum((x - mean) ** 2 for x in rets) / (len(rets) - 1))
        out["sharpe_ratio"] = mean / std * math.sqrt(252) if std > 0 else None

    # Win rate: net P&L per round trip, after commission and slippage.
    wins = closed = 0
    for buy, sell in zip(result.fills[::2], result.fills[1::2]):
        cost = buy.price * buy.quantity + buy.commission
        proceeds = sell.price * sell.quantity - sell.commission
        closed += 1
        wins += proceeds > cost
    out["win_rate"] = wins / closed if closed else None

    first_open, last_close = bars[0]["open"], bars[-1]["close"]
    if first_open > 0:
        out["buy_and_hold_return"] = float(last_close / first_open - 1)
    return out
