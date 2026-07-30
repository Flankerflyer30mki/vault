import redis
import json
import os

redis_client = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    decode_responses=True
)


def set_progress(run_id, processed, total):
    key = f"progress:{run_id}"
    value = json.dumps({"processed": processed, "total": total})
    try:
        redis_client.set(key, value, ex=3600)
    except redis.exceptions.RedisError:
        pass  # Redis unavailable — progress tracking is best-effort, not critical


def get_progress(run_id):
    key = f"progress:{run_id}"
    try:
        value = redis_client.get(key)
    except redis.exceptions.RedisError:
        return None  # treat "Redis unreachable" the same as "no progress recorded yet"
    if value:
        return json.loads(value)
    return None


def clear_progress(run_id):
    key = f"progress:{run_id}"
    try:
        redis_client.delete(key)
    except redis.exceptions.RedisError:
        pass