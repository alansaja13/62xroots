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
    prefetched = getattr(planta, "_prefetched_objects_cache", {}).get("cambios_etapa")
    if prefetched is not None:
        vigentes = [c for c in prefetched if c.fecha_inicio <= fecha]
        return max(vigentes, key=lambda c: (c.fecha_inicio, c.pk), default=None)
    return (
        planta.cambios_etapa
        .filter(fecha_inicio__lte=fecha)
        .order_by("-fecha_inicio", "-pk")
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
    Si no hay plantas activas o ninguna resuelve etapa, cae al estado del cultivo.

    Se memoriza en la instancia: listar mediciones evalúa la etapa de cada una
    y, sin esto, cada fila recorría todas las plantas y sus cambios de etapa.
    """
    from django.utils import timezone
    fecha = fecha or timezone.localdate()
    memo = cultivo.__dict__.setdefault("_etapa_por_fecha", {})
    if fecha not in memo:
        plantas = cultivo.__dict__.get("_plantas_para_etapa")
        if plantas is None:
            plantas = list(cultivo.plantas.activas().prefetch_related("cambios_etapa"))
            cultivo.__dict__["_plantas_para_etapa"] = plantas
        etapas = [e for e in (etapa_efectiva_planta(p, fecha) for p in plantas) if e]
        memo[fecha] = (max(etapas, key=ETAPA_ORDEN.index) if etapas
                       else DEFAULT_ETAPA_POR_ESTADO_CULTIVO.get(cultivo.estado))
    return memo[fecha]


def parametro_ideal_de(cultivo, etapa):
    """ParametroIdeal de la etapa, memorizado en la instancia del cultivo."""
    from .models import ParametroIdeal
    memo = cultivo.__dict__.setdefault("_parametro_por_etapa", {})
    if etapa not in memo:
        memo[etapa] = ParametroIdeal.objects.filter(etapa=etapa).first()
    return memo[etapa]
