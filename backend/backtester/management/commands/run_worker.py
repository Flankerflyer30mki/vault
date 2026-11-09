import signal

from django.core.management.base import BaseCommand

from backtester.jobs import work_forever


class Command(BaseCommand):
    help = "Process queued backtests, one at a time. Run more worker processes to scale."

    def handle(self, *args, **options):
        stopping = []
        signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))  # finish the current job, then exit
        work_forever(stop=lambda: bool(stopping))
