import redis
import json
import os
from backtester.models import Bar

redis_client = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    decode_responses=True
)


def get_sma(symbol, window, start_date, end_date):
    cache_key = f"indicator:{symbol}:sma:{window}:{start_date}:{end_date}"

    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except redis.exceptions.RedisError:
        pass  # Redis unavailable — just recompute instead of using cache

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

    try:
        redis_client.set(cache_key, json.dumps(sma_values), ex=3600)
    except redis.exceptions.RedisError:
        pass  # caching is a nice-to-have, not required for correctness

    return sma_values