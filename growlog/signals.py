"""Limpieza de archivos: una foto sin medición queda privada pero huérfana en el bucket."""
import logging

from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import MedicionPlanta

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
