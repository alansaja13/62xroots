"""Etapa del cultivo: única fuente de la que salen el estado, el día de flora y el VPD ideal."""
from django.db import transaction
from django.utils import timezone

from ..models import CambioEtapaCultivo
from ..utils import olvidar_etapas

ETAPAS_FLORA = ("flora_temprana", "flora_tardia")

# Estado administrativo (el que ven los listados) que corresponde a cada etapa.
ESTADO_POR_ETAPA = {
    "plantula": "plantula",
    "veg_temprano": "vegetativo",
    "veg_tardio": "vegetativo",
    "flora_temprana": "floracion",
    "flora_tardia": "floracion",
    "secado": "secado",
    "curado": "curado",
}


def sincronizar_cultivo(cultivo):
    """Recalcula lo derivado del historial de etapas: el estado vigente y el inicio de
    flora (la primera etapa de flora de todas, así pasar de flora temprana a tardía
    no reinicia el contador). Sin historial no hay inicio de flora; el estado queda como está.
    """
    olvidar_etapas(cultivo)
    cambios = list(cultivo.cambios_etapa.order_by("fecha_inicio"))
    flora = [c.fecha_inicio for c in cambios if c.etapa in ETAPAS_FLORA]
    cultivo.fecha_inicio_flora = min(flora) if flora else None
    campos = ["fecha_inicio_flora"]
    vigentes = [c for c in cambios if c.fecha_inicio <= timezone.localdate()]
    if vigentes and cultivo.estado != "finalizado":
        cultivo.estado = ESTADO_POR_ETAPA[vigentes[-1].etapa]
        campos.append("estado")
    cultivo.save(update_fields=campos)


@transaction.atomic
def reabrir_cultivo(cultivo):
    """Deshace finalizar: quita la fecha de cierre y recupera el estado desde el
    historial de etapas. Sin historial queda en vegetativo hasta que se cambie la etapa."""
    cultivo.estado = "vegetativo"
    cultivo.fecha_fin = None
    cultivo.save(update_fields=["estado", "fecha_fin"])
    sincronizar_cultivo(cultivo)


@transaction.atomic
def cambiar_etapa(cultivo, etapa, fecha, notas=""):
    """Registra que el cultivo está en `etapa` desde `fecha`. Repetir la misma fecha
    corrige el registro de ese día en vez de fallar."""
    cambio, _ = CambioEtapaCultivo.objects.update_or_create(
        cultivo=cultivo, fecha_inicio=fecha, defaults={"etapa": etapa, "notas": notas},
    )
    sincronizar_cultivo(cultivo)
    return cambio
