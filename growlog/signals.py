"""Limpieza de archivos (una foto sin medición queda huérfana en el bucket) y registro de ingresos."""
import logging
from datetime import timedelta

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Ingreso, MedicionPlanta

logger = logging.getLogger(__name__)


def _borrar_archivo_al_confirmar(storage, name):
    if not name:
        return

    def borrar():
        try:
            storage.delete(name)
        except Exception:  # un fallo del storage no debe romper la operación ya confirmada
            logger.exception("No se pudo borrar el archivo %s", name)

    transaction.on_commit(borrar)


@receiver(post_delete, sender=MedicionPlanta)
def borrar_foto_de_medicion(sender, instance, **kwargs):
    if instance.foto:
        _borrar_archivo_al_confirmar(instance.foto.storage, instance.foto.name)


@receiver(pre_save, sender=MedicionPlanta)
def borrar_foto_reemplazada(sender, instance, **kwargs):
    if not instance.pk:
        return
    anterior = sender.objects.filter(pk=instance.pk).values_list("foto", flat=True).first()
    if anterior and anterior != instance.foto.name:
        _borrar_archivo_al_confirmar(instance.foto.storage, anterior)


# ── Ingresos ────────────────────────────────────────────────────────────────
DIAS_INGRESOS = 90

SISTEMAS = [("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
            ("Macintosh", "Mac"), ("CrOS", "ChromeOS"), ("Linux", "Linux")]
# El orden importa: Edge y Opera dicen "Chrome", y Chrome dice "Safari".
NAVEGADORES = [("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung"), ("Firefox", "Firefox"),
               ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome", "Chrome"), ("Safari", "Safari")]


def dispositivo_corto(user_agent):
    """"iPhone · Safari" a partir del User-Agent; vacío si no se reconoce."""
    sistema = next((nombre for clave, nombre in SISTEMAS if clave in user_agent), "")
    navegador = next((nombre for clave, nombre in NAVEGADORES if clave in user_agent), "")
    return " · ".join(p for p in (sistema, navegador) if p)


def _dispositivo(request):
    return dispositivo_corto(request.META.get("HTTP_USER_AGENT", "")) if request is not None else ""


@receiver(user_logged_in)
def registrar_ingreso(sender, request, user, **kwargs):
    Ingreso.objects.create(usuario=user, nombre_usado=user.get_username(), exito=True,
                           dispositivo=_dispositivo(request))
    # La tabla se poda sola: con un borrado por login alcanza y no hace falta un cron.
    Ingreso.objects.filter(creado_en__lt=timezone.now() - timedelta(days=DIAS_INGRESOS)).delete()


@receiver(user_login_failed)
def registrar_ingreso_fallido(sender, credentials, request=None, **kwargs):
    Ingreso.objects.create(nombre_usado=(credentials.get("username") or "")[:150], exito=False,
                           dispositivo=_dispositivo(request))
