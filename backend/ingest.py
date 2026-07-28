import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vault_core.settings')
django.setup()

import yfinance as yf
from backtester.models import Bar

SYMBOLS = ['AAPL', 'MSFT', 'TSLA', 'SPY', 'GOOGL']

for symbol in SYMBOLS:
    print(f"Fetching {symbol}...")
    df = yf.download(symbol, period="3y", interval="1d", progress=False)

    bars = []
    for date, row in df.iterrows():
        bars.append(Bar(
            symbol=symbol,
            ts=timezone.make_aware(date.to_pydatetime()),
            open=float(row['Open'].iloc[0]) if hasattr(row['Open'], 'iloc') else float(row['Open']),
            high=float(row['High'].iloc[0]) if hasattr(row['High'], 'iloc') else float(row['High']),
            low=float(row['Low'].iloc[0]) if hasattr(row['Low'], 'iloc') else float(row['Low']),
            close=float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close']),
            volume=int(row['Volume'].iloc[0]) if hasattr(row['Volume'], 'iloc') else int(row['Volume'])
        ))

    Bar.objects.bulk_create(bars, ignore_conflicts=True)
    print(f"Inserted {len(bars)} bars for {symbol}")

print("Done.")