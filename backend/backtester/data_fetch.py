"""Market data: coverage check, idempotent fetch, validation. Runs inside the worker, never in a request.

Adjusted prices (auto_adjust=True) are restated by the provider after every split and dividend, so bars
fetched at different times can be on different price scales. To keep one symbol's history on a single
scale, every fetch re-downloads the symbol's whole known span and replaces its stored bars.
"""
import hashlib
import logging
import math
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Min
from django.utils import timezone

from backtester.engine import WARMUP_BARS
from backtester.models import Bar, SymbolCoverage

log = logging.getLogger(__name__)
PROVIDER = {"provider": "yahoo", "adjusted": True, "interval": "1d"}
MAX_GAP_DAYS = 5      # longest normal weekend + holiday run; longer gaps are reported
EDGE_SLACK_DAYS = 5
WARMUP_CALENDAR_PER_BAR = 2  # ~2 calendar days per trading day covers weekends and holidays
# Plus a fixed week: with few warm-up bars, 2 days per bar can land entirely on a weekend or holiday (1 bar before
# Monday 2024-01-01 looked only at Sat 30 and Sun 31 Dec). Only the last `warmup_bars` bars are used, so the extra
# days never change what a strategy sees when the shorter window already had enough.
WARMUP_MARGIN_DAYS = 7


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


def _day_start(d):
    return datetime.combine(d, time(), tzinfo=UTC)


def _query(symbol, start, end):
    # Half-open range on ts itself (not ts__date) so the (symbol, ts) index is usable.
    return list(Bar.objects.filter(symbol=symbol, ts__gte=_day_start(start),
                                   ts__lt=_day_start(end + timedelta(days=1))).order_by("ts"))


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


def _covered(symbol, start, end):
    cov = SymbolCoverage.objects.filter(symbol=symbol).first()
    return cov is not None and cov.start <= start and end <= cov.until


def _refresh(symbol, start, end, fetch):
    """Download the union of the requested span and everything already stored or covered for the symbol,
    then replace the symbol's bars in one transaction. Returns the number of rejected provider rows."""
    cov = SymbolCoverage.objects.filter(symbol=symbol).first()
    stored = Bar.objects.filter(symbol=symbol).aggregate(lo=Min("ts"), hi=Max("ts"))
    starts, ends = [start], [end]
    if cov:
        starts.append(cov.start)
        ends.append(cov.until)
    if stored["lo"]:
        starts.append(stored["lo"].date())
        ends.append(stored["hi"].date())
    span_start, span_end = min(starts), max(ends)
    try:
        fetched, rejected = fetch(symbol, span_start, span_end)
    except Exception as e:
        log.warning("event=fetch_failed symbol=%s error=%s", symbol, type(e).__name__)
        return 0
    if not fetched:
        # Unknown ticker or provider hiccup: keep what is stored and do not record coverage, so a later
        # request tries again.
        log.warning("event=fetch_empty symbol=%s", symbol)
        return rejected
    now = timezone.now()
    with transaction.atomic():
        Bar.objects.filter(symbol=symbol, ts__gte=_day_start(span_start),
                           ts__lt=_day_start(span_end + timedelta(days=1))).delete()
        Bar.objects.bulk_create(fetched, update_conflicts=True, unique_fields=["symbol", "ts"],
                                update_fields=["open", "high", "low", "close", "volume"])
        # Only days before the fetch day are final; today's bar may not exist yet.
        until = min(span_end, now.date() - timedelta(days=1))
        SymbolCoverage.objects.update_or_create(
            symbol=symbol, defaults={"start": span_start, "until": until, "fetched_at": now})
    log.info("event=bars_refreshed symbol=%s start=%s end=%s bars=%s", symbol, span_start, span_end, len(fetched))
    return rejected


def load_bars(symbol, start, end, fetch=None, warmup_bars=WARMUP_BARS):
    """Returns (warmup_bars, bars, manifest). Fetches from the provider only when the span was never fetched.
    Partial data is allowed but labelled in manifest['warnings']; no bars at all raises DataError.
    warmup_bars: bars needed before `start` (50 for code strategies; builder strategies ask for their longest lookback)."""
    end = min(end, datetime.now(UTC).date())
    warm_start = start - timedelta(days=warmup_bars * WARMUP_CALENDAR_PER_BAR + WARMUP_MARGIN_DAYS)
    rejected = 0
    if not _covered(symbol, warm_start, end):
        rejected = _refresh(symbol, warm_start, end, fetch or download)  # looked up per call so tests can patch it

    rows = _query(symbol, warm_start, end)
    warmup = [b for b in rows if b.ts.date() < start][-warmup_bars:]
    bars = [b for b in rows if b.ts.date() >= start]
    if not bars:
        raise DataError(f"No market data for '{symbol}' between {start} and {end}. Check the ticker.")

    warnings = coverage_warnings(bars, start, end)
    if len(warmup) < warmup_bars:
        warnings.append(f"only {len(warmup)} of {warmup_bars} warm-up bars before start; indicators start late")
    if rejected:
        warnings.append(f"{rejected} provider rows rejected (invalid OHLC)")
    digest = hashlib.sha256("".join(f"{b.ts.date()},{b.open},{b.high},{b.low},{b.close};" for b in warmup + bars)
                            .encode()).hexdigest()
    manifest = {**PROVIDER, "symbol": symbol, "first_bar": str(bars[0].ts.date()), "last_bar": str(bars[-1].ts.date()),
                "bar_count": len(bars), "warmup_bars": len(warmup), "data_sha256": digest, "warnings": warnings}
    return warmup, bars, manifest
