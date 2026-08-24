import logging

logger = logging.getLogger(__name__)

_scheduler = None


def start():
    """Arranca el scheduler en proceso (una sola vez por proceso).

    Corre el recordatorio diario de medición a la hora configurada en
    RECORDATORIO_MEDICION_HORA. Ver growlog/apps.py para las guardas que
    evitan arrancarlo dos veces (autoreload) o durante management commands.
    """
    global _scheduler
    if _scheduler is not None:
        return

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from django.conf import settings

    _scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    _scheduler.add_job(
        _job_recordatorio_medicion,
        CronTrigger(hour=settings.RECORDATORIO_MEDICION_HORA, minute=0),
        id="recordatorio_medicion",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler de recordatorios iniciado (corre a las %02d:00 %s).",
        settings.RECORDATORIO_MEDICION_HORA, settings.TIME_ZONE,
    )


def _job_recordatorio_medicion():
    from django.core.management import call_command
    call_command("send_recordatorios")
