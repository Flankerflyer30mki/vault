import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vault_core.settings')
django.setup()

import json
import time
from kafka import KafkaProducer
from backtester.models import Bar

SYMBOL = 'AAPL'

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

bars = Bar.objects.filter(symbol=SYMBOL).order_by('ts')

print(f"Replaying {bars.count()} bars for {SYMBOL}...")

for bar in bars:
    message = {
        'symbol': bar.symbol,
        'ts': bar.ts.isoformat(),
        'open': float(bar.open),
        'high': float(bar.high),
        'low': float(bar.low),
        'close': float(bar.close),
        'volume': bar.volume
    }
    producer.send('bar-replay', message)
    print(f"Sent: {bar.ts.date()} close={bar.close}")
    time.sleep(0.05)  # small delay so you can watch it stream, not required in production

producer.flush()
print("Replay complete.")