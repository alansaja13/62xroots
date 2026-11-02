"""Datos de Aire: lecturas de ambiente y de pH/EC de un rango, con los rangos ideales por etapa."""
from datetime import timedelta

from django.utils import timezone

from ..models import MedicionEC, ParametroIdeal, Riego, RiegoPlanta
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
        "ph": [float(p.ph_min), float(p.ph_max)],
        # La EC se muestra en µS/cm (en la base está en mS/cm).
        "ec": [float(p.ec_min) * 1000, float(p.ec_max) * 1000] if p.ec_min is not None and p.ec_max is not None else None,
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
        "ph_ec": lecturas_ph_ec(cultivo, dias),
        "etapas": etapas_ideales(),
        "etapa_actual": etapa_efectiva_cultivo(cultivo),
        "en_rango": _porcentaje(lecturas),
        "en_rango_dia": _porcentaje([l for l in lecturas if l["luz"] == "on"]),
        "en_rango_noche": _porcentaje([l for l in lecturas if l["luz"] == "off"]),
    }


def lecturas_ph_ec(cultivo, dias):
    """pH y EC del rango: mediciones sueltas, solución de cada riego y runoff por planta.
    `fuente` dice de dónde sale cada punto; la EC va en µS/cm."""
    desde = timezone.now() - timedelta(days=dias) if dias is not None else None
    puntos = []

    def agregar(ts, ph, ec, fuente, detalle=""):
        if ph is None and ec is None:
            return
        puntos.append({
            "ts": timezone.localtime(ts).isoformat(), "fuente": fuente, "detalle": detalle,
            "ph": float(ph) if ph is not None else None, "ec": float(ec) * 1000 if ec is not None else None,
            "etapa": etapa_efectiva_cultivo(cultivo, timezone.localdate(ts)),
        })

    mediciones = MedicionEC.objects.filter(cultivo=cultivo)
    riegos = Riego.objects.filter(cultivo=cultivo)
    runoff = RiegoPlanta.objects.filter(riego__cultivo=cultivo, runoff_observado=True).select_related("riego", "planta")
    if desde:
        mediciones, riegos = mediciones.filter(timestamp__gte=desde), riegos.filter(timestamp__gte=desde)
        runoff = runoff.filter(riego__timestamp__gte=desde)
    for m in mediciones[:MAX_LECTURAS]:
        agregar(m.timestamp, m.ph, m.ec, {"solucion": "solucion", "runoff": "runoff"}.get(m.tipo, m.tipo), m.get_tipo_display())
    for r in riegos[:MAX_LECTURAS]:
        agregar(r.timestamp, r.ph_agua, r.ec_solucion, "solucion", "riego")
    for rp in runoff[:MAX_LECTURAS]:
        agregar(rp.riego.timestamp, rp.ph_runoff, rp.ec_runoff, "runoff", rp.planta.apodo)
    puntos.sort(key=lambda p: p["ts"])
    return puntos
