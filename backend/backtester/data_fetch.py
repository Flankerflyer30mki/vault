import yfinance as yf
from django.utils import timezone
from backtester.models import Bar


def ensure_symbol_data(symbol, start_date, end_date):
    """
    Checks if we have data for this symbol covering the requested range.
    If not, fetches it from Yahoo Finance and stores it.
    Returns True if data is now available, False if the symbol is invalid/no data found.
    """
    existing_count = Bar.objects.filter(
        symbol=symbol,
        ts__date__gte=start_date,
        ts__date__lte=end_date
    ).count()

    if existing_count > 0:
        return True  # already have data covering this range

    df = yf.download(symbol, start=start_date, end=end_date, interval="1d", progress=False)

    if df.empty:
        return False  # invalid symbol or no data available

    bars = []
    for date, row in df.iterrows():
        bars.append(Bar(
            symbol=symbol.upper(),
            ts=timezone.make_aware(date.to_pydatetime()),
            open=float(row['Open'].iloc[0]) if hasattr(row['Open'], 'iloc') else float(row['Open']),
            high=float(row['High'].iloc[0]) if hasattr(row['High'], 'iloc') else float(row['High']),
            low=float(row['Low'].iloc[0]) if hasattr(row['Low'], 'iloc') else float(row['Low']),
            close=float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close']),
            volume=int(row['Volume'].iloc[0]) if hasattr(row['Volume'], 'iloc') else int(row['Volume'])
        ))

    Bar.objects.bulk_create(bars, ignore_conflicts=True)
    return True