import json
import logging

from django.conf import settings
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)


def send_push_to_all(title, body, url="/"):
    """Manda una notificación push a todas las suscripciones activas.

    Devuelve la cantidad de suscripciones a las que se les envió con éxito.
    Suscripciones vencidas (404/410) se borran solas.
    """
    from .models import PushSubscription

    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY no configurada — no se puede enviar push.")
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    enviados = 0
    for sub in PushSubscription.objects.all():
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
            )
            enviados += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                sub.delete()
            else:
                logger.error("Error enviando push a %s: %s", sub.endpoint, e)
        except Exception:
            # Una suscripción con datos corruptos no debe frenar el envío al resto.
            logger.exception("Error inesperado enviando push a %s", sub.endpoint)
    return enviados
