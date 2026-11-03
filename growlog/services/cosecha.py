"""Cosecha guiada: cortar, pesar en húmedo, secar y cerrar el cultivo."""
from django.db import transaction
from django.utils import timezone

from ..utils import etapa_efectiva_cultivo
from .etapas import cambiar_etapa

PASOS = ("cortar", "pesar", "secar", "cerrar")


def plantas_de_cosecha(cultivo):
    """Las que entran en la cosecha: activas o ya cosechadas, sin las descartadas ni archivadas."""
    return list(cultivo.plantas.filter(archivado=False, estado__in=("activa", "cosechada")).order_by("apodo", "pk"))


def resumen(cultivo):
    plantas = plantas_de_cosecha(cultivo)
    cortadas = [p for p in plantas if p.fecha_corte]
    sin_cortar = [p for p in plantas if not p.fecha_corte]
    humedo = sum(p.peso_humedo_g or 0 for p in cortadas)
    seco = sum(p.yield_real_g or 0 for p in cortadas)
    hechos = {
        "cortar": bool(cortadas) and not sin_cortar,
        "pesar": bool(cortadas) and all(p.peso_humedo_g for p in cortadas),
        "secar": bool(cortadas) and all(p.yield_real_g for p in cortadas),
        "cerrar": cultivo.estado == "finalizado",
    }
    actual = next((paso for paso in PASOS if not hechos[paso]), "cerrar")
    watts = cultivo.lampara_watts_reales
    return {
        "plantas": plantas, "cortadas": cortadas, "sin_cortar": sin_cortar,
        "hechos": hechos, "actual": actual,
        "humedo_total": humedo, "seco_total": seco,
        # Lo que se pierde al secar, solo con las plantas pesadas en húmedo y en seco.
        "merma": _merma(cortadas),
        "g_por_watt": round(seco / float(watts), 2) if seco and watts else None,
        "etapa": etapa_efectiva_cultivo(cultivo),
    }


def _merma(plantas):
    pares = [(p.peso_humedo_g, p.yield_real_g) for p in plantas if p.peso_humedo_g and p.yield_real_g]
    humedo = sum(h for h, _ in pares)
    return round(100 * (1 - sum(s for _, s in pares) / humedo)) if humedo else None


@transaction.atomic
def cortar(cultivo, plantas, fecha, *, pasar_a_secado):
    for planta in plantas:
        planta.fecha_corte = fecha
        planta.estado = "cosechada"
        planta.save(update_fields=["fecha_corte", "estado"])
    if pasar_a_secado and etapa_efectiva_cultivo(cultivo) not in ("secado", "curado"):
        cambiar_etapa(cultivo, "secado", fecha)


@transaction.atomic
def pesar(pesos):
    """`pesos`: {planta: gramos o None}. None deja el peso como estaba."""
    for planta, gramos in pesos.items():
        if gramos is not None:
            planta.peso_humedo_g = gramos
            planta.save(update_fields=["peso_humedo_g"])


@transaction.atomic
def secar(cultivo, pesos, fecha, *, pasar_a_curado):
    for planta, gramos in pesos.items():
        if gramos is not None:
            planta.yield_real_g = gramos
            planta.fecha_seco = fecha
            planta.save(update_fields=["yield_real_g", "fecha_seco"])
    if pasar_a_curado and etapa_efectiva_cultivo(cultivo) != "curado":
        cambiar_etapa(cultivo, "curado", fecha)


def cerrar(cultivo):
    cultivo.estado = "finalizado"
    if not cultivo.fecha_fin:
        cultivo.fecha_fin = timezone.localdate()
    cultivo.save(update_fields=["estado", "fecha_fin"])
