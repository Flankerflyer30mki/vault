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
    redis_client.set(key, value, ex=3600)  # expires after 1 hour, no need to persist forever


def get_progress(run_id):
    key = f"progress:{run_id}"
    value = redis_client.get(key)
    if value:
        return json.loads(value)
    return None


def clear_progress(run_id):
    key = f"progress:{run_id}"
    redis_client.delete(key)