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


def resolver_luz_estado_para_medicion(cultivo, timestamp):
    """Returns 'on', 'off', or None if no CambioFotoperiodo is configured."""
    cambio = get_cambio_fotoperiodo_activo(cultivo, timestamp)
    if cambio is None:
        return None
    return calcular_luz_estado(timestamp, cambio.hora_lights_on, cambio.fotoperiodo)
