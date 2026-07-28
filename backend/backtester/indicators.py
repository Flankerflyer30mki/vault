import redis
import json
from backtester.models import Bar

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)


def get_sma(symbol, window, start_date, end_date):
    cache_key = f"indicator:{symbol}:sma:{window}:{start_date}:{end_date}"

    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    bars = list(Bar.objects.filter(
        symbol=symbol,
        ts__date__gte=start_date,
        ts__date__lte=end_date
    ).order_by('ts'))

    closes = [float(b.close) for b in bars]
    sma_values = []
    for i in range(len(closes)):
        if i < window - 1:
            sma_values.append(None)
        else:
            sma_values.append(sum(closes[i - window + 1:i + 1]) / window)

    redis_client.set(cache_key, json.dumps(sma_values), ex=3600)  # cache expires after 1 hour
    return sma_values