"""Ciclo del cultivo: cuánto duró (o lleva) cada fase contra lo estimado, y el flip."""
from datetime import time, timedelta

from django.db import transaction
from django.utils import timezone

from ..models import CambioFotoperiodo
from ..utils import get_cambio_fotoperiodo_activo
from .etapas import cambiar_etapa

# Fase → (nombre, etapas finas que incluye, días orientativos si no hay estimado propio)
FASES = [
    ("plantula", "Plántula", ("plantula",), None),
    ("veg", "Veg", ("veg_temprano", "veg_tardio"), None),
    ("flora", "Flora", ("flora_temprana", "flora_tardia"), None),
    ("secado", "Secado", ("secado",), 10),
    ("curado", "Curado", ("curado",), 21),
]
FOTOPERIODO_FLORA = "12/12"


def _fase_de(etapa):
    return next((clave for clave, _, etapas, _ in FASES if etapa in etapas), None)


def resumen_ciclo(cultivo, hoy=None):
    hoy = hoy or timezone.localdate()
    fin = min(cultivo.fecha_referencia, hoy)
    cambios = sorted(cultivo.cambios_etapa.all(), key=lambda c: (c.fecha_inicio, c.pk))

    # Días reales por fase, desde el inicio del cultivo, según los cambios de etapa.
    real = {}
    for i, cambio in enumerate(cambios):
        hasta = cambios[i + 1].fecha_inicio if i + 1 < len(cambios) else fin
        fase = _fase_de(cambio.etapa)
        if fase is None or hasta < cambio.fecha_inicio:
            continue
        desde_dia = (cambio.fecha_inicio - cultivo.fecha_inicio).days
        dias = (hasta - cambio.fecha_inicio).days
        anterior = real.get(fase)
        real[fase] = (min(anterior[0], desde_dia), anterior[1] + dias) if anterior else (desde_dia, dias)

    flora_estimada = cultivo.dias_flora_estimados or max(
        (p.dias_flora_estimados or 0 for p in cultivo.plantas.activas()), default=0) or None
    estimados = {"plantula": None, "veg": cultivo.dias_veg_estimados, "flora": flora_estimada}

    filas, cursor = [], 0
    for clave, nombre, _, orientativo in FASES:
        est = estimados.get(clave, orientativo)
        r = real.get(clave)
        if r is None and est is None:
            continue
        filas.append({"clave": clave, "nombre": nombre, "estimado": est, "orientativo": clave not in estimados,
                      "est_desde": cursor, "real_desde": r[0] if r else None, "real_dias": r[1] if r else None})
        cursor += est or (r[1] if r else 0)
    finales = [f["real_desde"] + f["real_dias"] for f in filas if f["real_desde"] is not None]
    total = max([cursor, cultivo.dias_desde_inicio] + finales) or 1
    for f in filas:
        f["est_izq"] = round(f["est_desde"] / total * 100, 2)
        f["est_ancho"] = round((f["estimado"] or 0) / total * 100, 2)
        if f["real_desde"] is not None:
            f["real_izq"] = round(f["real_desde"] / total * 100, 2)
            f["real_ancho"] = max(0.8, round(f["real_dias"] / total * 100, 2))

    fotoperiodo = get_cambio_fotoperiodo_activo(cultivo, timezone.now())
    snapshot = cultivo.canopy_snapshots.first()
    en_flora = bool(cultivo.fecha_inicio_flora)
    cosecha = cultivo.fecha_inicio_flora + timedelta(days=flora_estimada) if en_flora and flora_estimada else None
    return {
        "filas": filas, "hoy_pct": round(min(cultivo.dias_desde_inicio, total) / total * 100, 2), "total": total,
        "en_flora": en_flora, "fotoperiodo": fotoperiodo,
        "puede_flip": not en_flora and cultivo.estado != "finalizado",
        "scrog_pct": snapshot.scrog_fill_pct if snapshot else None,
        "cosecha_estimada": cosecha, "dias_a_cosecha": (cosecha - hoy).days if cosecha else None,
    }


@transaction.atomic
def hacer_flip(cultivo, fecha=None):
    """Pasar a floración en un paso: etapa flora temprana y fotoperíodo 12/12 desde `fecha`.
    Si ya estaba en flora no toca nada (el día de flora nunca se reinicia desde acá)."""
    fecha = fecha or timezone.localdate()
    if cultivo.fecha_inicio_flora:
        return False
    cambiar_etapa(cultivo, "flora_temprana", fecha, notas="Flip")
    actual = get_cambio_fotoperiodo_activo(cultivo, timezone.now())
    if actual is None or actual.fotoperiodo != FOTOPERIODO_FLORA:
        CambioFotoperiodo.objects.update_or_create(
            cultivo=cultivo, fecha_inicio=fecha,
            defaults={"fotoperiodo": FOTOPERIODO_FLORA,
                      "hora_lights_on": actual.hora_lights_on if actual else time(6), "notas": "Flip"},
        )
    return True
