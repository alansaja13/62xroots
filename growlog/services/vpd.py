"""Datos del mapa de VPD: lecturas de ambiente de un rango y los rangos ideales por etapa."""
from datetime import timedelta

from django.utils import timezone

from ..models import ParametroIdeal
from ..utils import ETAPA_ORDEN, etapa_efectiva_cultivo, parametro_ideal_de

# Rangos de tiempo que ofrece el mapa: clave → (etiqueta, días; None = todo el ciclo).
RANGOS = {"24h": ("24 h", 1), "7d": ("7 d", 7), "30d": ("30 d", 30), "ciclo": ("Ciclo", None)}
RANGO_DEFAULT = "7d"
MAX_LECTURAS = 600


def _rango(param):
    """(min, max) de VPD de una etapa, o None si la etapa no tiene un ideal de VPD (p. ej. secado en 0–0)."""
    if param is None or param.vpd_max <= param.vpd_min:
        return None
    return float(param.vpd_min), float(param.vpd_max)


def estado_vpd(vpd, rango):
    if rango is None:
        return None
    if rango[0] <= vpd <= rango[1]:
        return "ideal"
    return "bajo" if vpd < rango[0] else "alto"


def estado_de(cultivo, medicion):
    """Estado del VPD de una lectura con el ideal de la etapa en que se midió."""
    etapa = etapa_efectiva_cultivo(cultivo, timezone.localdate(medicion.timestamp))
    return estado_vpd(medicion.vpd, _rango(parametro_ideal_de(cultivo, etapa)) if etapa else None)


def etapas_ideales():
    """Rangos ideales de cada etapa cargada, en el orden del ciclo."""
    nombres = dict(ParametroIdeal.ETAPA_CHOICES)
    params = sorted(ParametroIdeal.objects.all(), key=lambda p: ETAPA_ORDEN.index(p.etapa) if p.etapa in ETAPA_ORDEN else 99)
    return [{
        "clave": p.etapa, "nombre": nombres.get(p.etapa, p.etapa),
        "temp": [float(p.temp_min), float(p.temp_max)], "hr": [float(p.hr_min), float(p.hr_max)],
        "vpd": _rango(p),
    } for p in params]


def _porcentaje(lecturas):
    juzgadas = [l for l in lecturas if l["estado"]]
    if not juzgadas:
        return None
    return round(100 * sum(l["estado"] == "ideal" for l in juzgadas) / len(juzgadas))


def mapa_vpd(cultivo, rango=RANGO_DEFAULT):
    if rango not in RANGOS:
        rango = RANGO_DEFAULT
    dias = RANGOS[rango][1]
    qs = cultivo.mediciones.order_by("-timestamp")
    if dias is not None:
        qs = qs.filter(timestamp__gte=timezone.now() - timedelta(days=dias))
    mediciones = list(qs[:MAX_LECTURAS])[::-1]

    lecturas = []
    for m in mediciones:
        # Cada lectura se juzga con la etapa vigente cuando se midió.
        fecha = timezone.localdate(m.timestamp)
        etapa = etapa_efectiva_cultivo(cultivo, fecha)
        rango_vpd = _rango(parametro_ideal_de(cultivo, etapa)) if etapa else None
        lecturas.append({
            "ts": timezone.localtime(m.timestamp).isoformat(),
            "t": float(m.temperatura_c), "h": float(m.humedad_relativa), "vpd": m.vpd,
            "luz": m.luz_estado, "etapa": etapa, "estado": estado_vpd(m.vpd, rango_vpd),
        })

    return {
        "rango": rango,
        "rangos": [{"clave": k, "etiqueta": v[0]} for k, v in RANGOS.items()],
        "lecturas": lecturas,
        "etapas": etapas_ideales(),
        "etapa_actual": etapa_efectiva_cultivo(cultivo),
        "en_rango": _porcentaje(lecturas),
        "en_rango_dia": _porcentaje([l for l in lecturas if l["luz"] == "on"]),
        "en_rango_noche": _porcentaje([l for l in lecturas if l["luz"] == "off"]),
    }
