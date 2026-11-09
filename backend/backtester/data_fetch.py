"""Market data: coverage check, idempotent fetch, validation. Runs inside the worker, never in a request."""
import hashlib
import logging
import math
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from backtester.engine import WARMUP_BARS
from backtester.models import Bar

log = logging.getLogger(__name__)
PROVIDER = {"provider": "yahoo", "adjusted": True, "interval": "1d"}
MAX_GAP_DAYS = 5      # longest normal weekend + holiday run; longer gaps are reported
EDGE_SLACK_DAYS = 5
WARMUP_CALENDAR_DAYS = WARMUP_BARS * 2  # ~100 calendar days covers 50 trading days


class DataError(Exception):
    """No usable data. Not retryable."""


def _to_bar(symbol, ts, o, h, low, c, v):
    """Returns a Bar, or None if the row breaks basic OHLC rules."""
    vals = [float(x) for x in (o, h, low, c)]
    if not all(math.isfinite(x) and x > 0 for x in vals):
        return None
    o, h, low, c = (Decimal(str(round(x, 4))) for x in vals)
    if low > min(o, c) or h < max(o, c):
        return None
    return Bar(symbol=symbol, ts=ts, open=o, high=h, low=low, close=c, volume=int(v or 0))


def download(symbol, start, end):
    """Fetch [start, end] inclusive. Yahoo's end is exclusive, hence +1 day. Returns (bars, rejected)."""
    import yfinance as yf
    df = yf.Ticker(symbol).history(start=start, end=end + timedelta(days=1), interval="1d",
                                   auto_adjust=True, timeout=15)
    bars, rejected = [], 0
    for idx, row in df.iterrows():
        ts = datetime.combine(idx.date(), time(), tzinfo=UTC)
        bar = _to_bar(symbol, ts, row["Open"], row["High"], row["Low"], row["Close"], row["Volume"])
        if bar is None:
            rejected += 1
        else:
            bars.append(bar)
    return bars, rejected


def _query(symbol, start, end):
    return list(Bar.objects.filter(symbol=symbol, ts__date__gte=start, ts__date__lte=end).order_by("ts"))


def coverage_warnings(bars, start, end):
    if not bars:
        return ["no bars in range"]
    out = []
    first, last = bars[0].ts.date(), bars[-1].ts.date()
    if (first - start).days > EDGE_SLACK_DAYS:
        out.append(f"data starts {first}, requested {start}")
    if (end - last).days > EDGE_SLACK_DAYS:
        out.append(f"data ends {last}, requested {end}")
    for a, b in zip(bars, bars[1:]):
        if (b.ts - a.ts).days > MAX_GAP_DAYS:
            out.append(f"gap {a.ts.date()} -> {b.ts.date()}")
    return out


def load_bars(symbol, start, end, fetch=download):
    """Returns (warmup_bars, bars, manifest). Fetches from the provider only when coverage is incomplete.
    Partial data is allowed but labelled in manifest['warnings']; no bars at all raises DataError."""
    end = min(end, datetime.now(UTC).date())
    warm_start = start - timedelta(days=WARMUP_CALENDAR_DAYS)
    rejected = 0
    if coverage_warnings(_query(symbol, warm_start, end), warm_start, end):
        try:
            fetched, rejected = fetch(symbol, warm_start, end)
        except Exception as e:
            log.warning("event=fetch_failed symbol=%s error=%s", symbol, type(e).__name__)
            fetched = []
        Bar.objects.bulk_create(fetched, ignore_conflicts=True)  # unique (symbol, ts): concurrent fetches are safe

    rows = _query(symbol, warm_start, end)
    warmup = [b for b in rows if b.ts.date() < start][-WARMUP_BARS:]
    bars = [b for b in rows if b.ts.date() >= start]
    if not bars:
        raise DataError(f"No market data for '{symbol}' between {start} and {end}. Check the ticker.")

    warnings = coverage_warnings(bars, start, end)
    if len(warmup) < WARMUP_BARS:
        warnings.append(f"only {len(warmup)} warm-up bars before start; SMA-{WARMUP_BARS} starts late")
    if rejected:
        warnings.append(f"{rejected} provider rows rejected (invalid OHLC)")
    digest = hashlib.sha256("".join(f"{b.ts.date()},{b.open},{b.high},{b.low},{b.close};" for b in warmup + bars)
                            .encode()).hexdigest()
    manifest = {**PROVIDER, "symbol": symbol, "first_bar": str(bars[0].ts.date()), "last_bar": str(bars[-1].ts.date()),
                "bar_count": len(bars), "warmup_bars": len(warmup), "data_sha256": digest, "warnings": warnings}
    return warmup, bars, manifest
