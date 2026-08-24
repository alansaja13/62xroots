import os
import sys

from django.apps import AppConfig


class GrowlogConfig(AppConfig):
    name = 'growlog'

    def ready(self):
        argv = sys.argv
        is_runserver = len(argv) > 1 and argv[1] == "runserver"
        is_gunicorn = bool(argv) and "gunicorn" in argv[0]

        if not (is_runserver or is_gunicorn):
            return  # migrate / shell / test / seed.py / etc. — no arrancar el scheduler

        if is_runserver and os.environ.get("RUN_MAIN") != "true":
            return  # proceso watcher del autoreload — el hijo lo arranca

        from . import scheduler
        scheduler.start()
