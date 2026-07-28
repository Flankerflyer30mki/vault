import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)


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