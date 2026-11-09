import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
timeout = 30
accesslog = "-"


def post_worker_init(worker):
    # ponytail: free-tier fallback when no separate worker service can be afforded.
    # One queue consumer thread per gunicorn worker; the queue is still durable in Postgres.
    if os.environ.get("EMBEDDED_WORKER") == "1":
        import threading

        from backtester.jobs import work_forever
        threading.Thread(target=work_forever, daemon=True, name="embedded-worker").start()
