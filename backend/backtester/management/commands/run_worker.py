import signal

from django.conf import settings
from django.core.management.base import BaseCommand

from backtester.jobs import SHUTDOWN, work_forever


class Command(BaseCommand):
    help = "Process queued backtests, one at a time. Run more worker processes to scale."

    def handle(self, *args, **options):
        # SIGTERM (a deploy or scale-down) and SIGINT (Ctrl+C): claim nothing new; the run in progress may finish within
        # WORKER_GRACE_S, after which it goes straight back to the queue (D-074). Render kills the process 30 s after
        # SIGTERM, so the default grace of 20 s leaves room to write the requeue.
        def stop(*_):
            SHUTDOWN.request(settings.VAULT["WORKER_GRACE_S"])

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        work_forever()
