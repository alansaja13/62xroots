import zoneinfo

ARGENTINA_TZ = zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires")


def get_cambio_fotoperiodo_activo(cultivo, timestamp):
    """Returns the most recent CambioFotoperiodo active at timestamp, or None."""
    from .models import CambioFotoperiodo
    if timestamp.tzinfo is None:
        ts_local = timestamp.replace(tzinfo=ARGENTINA_TZ)
    else:
        ts_local = timestamp.astimezone(ARGENTINA_TZ)
    return (
        CambioFotoperiodo.objects
        .filter(cultivo=cultivo, fecha_inicio__lte=ts_local.date())
        .order_by("-fecha_inicio")
        .first()
    )


def calcular_luz_estado(timestamp, hora_lights_on, fotoperiodo):
    """Returns 'on' or 'off' based on Argentina local time."""
    if timestamp.tzinfo is None:
        ts_local = timestamp.replace(tzinfo=ARGENTINA_TZ)
    else:
        ts_local = timestamp.astimezone(ARGENTINA_TZ)

    horas_luz = int(fotoperiodo.split("/")[0])
    current_min = ts_local.hour * 60 + ts_local.minute
    on_min = hora_lights_on.hour * 60 + hora_lights_on.minute
    off_min = (on_min + horas_luz * 60) % (24 * 60)

    if on_min < off_min:
        return "on" if on_min <= current_min < off_min else "off"
    else:
        # Wrap-around past midnight
        return "on" if current_min >= on_min or current_min < off_min else "off"


def get_flip_a_flora(cultivo):
    """Primer CambioFotoperiodo con ≤12h de luz (el "flip" a floración), o None."""
    from .models import CambioFotoperiodo
    for cambio in CambioFotoperiodo.objects.filter(cultivo=cultivo).order_by("fecha_inicio"):
        try:
            horas_luz = int(cambio.fotoperiodo.split("/")[0])
        except (ValueError, IndexError):
            continue
        if horas_luz <= 12:
            return cambio
    return None


def resolver_luz_estado_para_medicion(cultivo, timestamp):
    """Returns 'on', 'off', or None if no CambioFotoperiodo is configured."""
    cambio = get_cambio_fotoperiodo_activo(cultivo, timestamp)
    if cambio is None:
        return None
    return calcular_luz_estado(timestamp, cambio.hora_lights_on, cambio.fotoperiodo)


ETAPA_ORDEN = [
    "plantula", "veg_temprano", "veg_tardio",
    "flora_temprana", "flora_tardia", "secado", "curado",
]

# Fallback para plantas sin CambioEtapaPlanta todavía, mapeado desde el estado
# administrativo (coarse) del cultivo. "finalizado" no tiene etapa de ambiente.
DEFAULT_ETAPA_POR_ESTADO_CULTIVO = {
    "plantula": "plantula",
    "vegetativo": "veg_temprano",
    "floracion": "flora_temprana",
    "secado": "secado",
    "curado": "curado",
    "finalizado": None,
}


def get_etapa_activa_planta(planta, fecha=None):
    """Devuelve el CambioEtapaPlanta vigente para `planta` en `fecha` (hoy por defecto), o None."""
    from django.utils import timezone
    fecha = fecha or timezone.localdate()
    return (
        planta.cambios_etapa
        .filter(fecha_inicio__lte=fecha)
        .order_by("-fecha_inicio")
        .first()
    )


def etapa_efectiva_planta(planta, fecha=None):
    """Etapa vigente de la planta: su historial si tiene, si no el default
    mapeado desde el estado administrativo del cultivo."""
    cambio = get_etapa_activa_planta(planta, fecha)
    if cambio is not None:
        return cambio.etapa
    return DEFAULT_ETAPA_POR_ESTADO_CULTIVO.get(planta.cultivo.estado)


def etapa_efectiva_cultivo(cultivo, fecha=None):
    """Etapa más avanzada entre las plantas activas del cultivo (el ambiente
    compartido se ajusta a la planta que más lo necesita, no al promedio).
    Si no hay plantas activas o ninguna resuelve etapa, cae al estado del cultivo."""
    etapas = [
        e for e in (
            etapa_efectiva_planta(p, fecha)
            for p in cultivo.plantas.filter(estado="activa")
        ) if e
    ]
    if not etapas:
        return DEFAULT_ETAPA_POR_ESTADO_CULTIVO.get(cultivo.estado)
    return max(etapas, key=ETAPA_ORDEN.index)
