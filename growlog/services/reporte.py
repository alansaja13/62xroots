"""Reporte de un cultivo: cifras de cierre, ambiente en rango, crecimiento, yield y comparación con otros."""
from datetime import timedelta

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from ..models import Cultivo, Evento, NutrienteAplicado, ParametroIdeal
from ..permissions import tarifas_del_cultivo
from ..utils import get_flip_a_flora
from .energia import calcular_meses
from .plantas import curva
from .vpd import estado_de

# Cuántos cultivos anteriores entran en la comparación.
ANTERIORES = 5
# Medidas de los gráficos (en unidades del viewBox).
ANCHO, ALTO = 320, 120


def _fechas(cultivo):
    fin = cultivo.fecha_fin or timezone.localdate()
    flip = cultivo.fecha_inicio_flora
    if not flip:
        cambio = get_flip_a_flora(cultivo)
        flip = cambio.fecha_inicio if cambio else None
    veg = flora = None
    if flip and flip >= cultivo.fecha_inicio:
        veg, flora = (flip - cultivo.fecha_inicio).days, max(0, (fin - flip).days)
    return fin, (fin - cultivo.fecha_inicio).days, veg, flora


def _en_rango(cultivo, mediciones):
    """% de lecturas con VPD en el ideal de su etapa, en total, de día y de noche, y por semana del ciclo."""
    juzgadas = [(m, estado_de(cultivo, m)) for m in mediciones]
    juzgadas = [(m, e) for m, e in juzgadas if e]

    def pct(lista):
        return round(100 * sum(e == "ideal" for _, e in lista) / len(lista)) if lista else None

    semanas = {}
    for m, e in juzgadas:
        semanas.setdefault((timezone.localdate(m.timestamp) - cultivo.fecha_inicio).days // 7, []).append((m, e))
    return {
        "total": pct(juzgadas),
        "dia": pct([(m, e) for m, e in juzgadas if m.luz_estado == "on"]),
        "noche": pct([(m, e) for m, e in juzgadas if m.luz_estado == "off"]),
        "semanas": [{"semana": s + 1, "pct": pct(v), "lecturas": len(v)} for s, v in sorted(semanas.items())],
    }


def _barras_semanas(semanas):
    if not semanas:
        return []
    paso = ANCHO / max(len(semanas), 1)
    return [{**s, "x": round(i * paso + 1, 1), "ancho": round(max(paso - 2, 1), 1),
             "alto": round(ALTO * s["pct"] / 100, 1), "y": round(ALTO - ALTO * s["pct"] / 100, 1)}
            for i, s in enumerate(semanas)]


def _crecimiento(cultivo, plantas):
    """Altura de cada planta por día del cultivo, como líneas en el mismo eje."""
    series = []
    for p in plantas:
        puntos = [((m.fecha - cultivo.fecha_inicio).days, float(m.altura_cm))
                  for m in p.mediciones.order_by("fecha") if m.altura_cm is not None]
        if len(puntos) >= 2:
            series.append((p, puntos))
    if not series:
        return None
    todos = [pt for _, pts in series for pt in pts]
    # Escala común: se suman las esquinas del rango a cada serie para que curva() use el mismo eje.
    d0, d1 = min(d for d, _ in todos), max(d for d, _ in todos)
    v0, v1 = 0, max(v for _, v in todos)
    lineas = []
    for p, pts in series:
        coords = curva([(d0, v0)] + pts + [(d1, v1)], ANCHO, ALTO)[1:-1]
        lineas.append({"planta": p, "puntos": " ".join(f"{x},{y}" for x, y in coords),
                       "ultima": pts[-1][1], "fin": coords[-1]})
    return {"lineas": lineas, "max": round(v1), "dia_desde": d0, "dia_hasta": d1}


def _energia(cultivo, fin, seco):
    costos = list(cultivo.costos_energeticos.select_related("equipo").order_by("fecha_desde"))
    tarifas = list(tarifas_del_cultivo(cultivo).filter(fecha_desde__lte=fin).order_by("-fecha_desde"))
    kwh = costo = None
    fuente = None
    if costos:
        meses = calcular_meses(cultivo.fecha_inicio, costos, tarifas, fin)
        kwh = round(sum(m["kwh_estimado"] for m in meses), 1)
        costo = round(sum(m["costo_estimado"] for m in meses)) if tarifas else None
        fuente = "equipos"
    lecturas = list(cultivo.lecturas_medidor.filter(fecha__lte=fin))
    if lecturas:
        kwh = round(float(sum(l.kwh_real for l in lecturas)), 1)
        costo = round(kwh * float(tarifas[0].precio_kwh)) if tarifas else None
        fuente = "medidor"
    elif not costos and cultivo.lampara_watts_reales:
        kwh = round(_kwh_lampara(cultivo, fin), 1)
        fuente = "lampara"
    return {"kwh": kwh, "costo": costo, "fuente": fuente,
            "costo_por_gramo": round(costo / seco) if costo and seco else None,
            "g_por_kwh": round(seco / kwh, 2) if seco and kwh else None}


def _kwh_lampara(cultivo, fin):
    """Sin equipos cargados: la lámpara del cultivo, con las horas de luz de cada fotoperíodo."""
    cambios = sorted(cultivo.cambios_fotoperiodo.all(), key=lambda c: c.fecha_inicio)
    total, watts = 0.0, float(cultivo.lampara_watts_reales)
    for i, c in enumerate(cambios):
        desde = max(c.fecha_inicio, cultivo.fecha_inicio)
        hasta = min(cambios[i + 1].fecha_inicio, fin + timedelta(days=1)) if i + 1 < len(cambios) else fin + timedelta(days=1)
        try:
            horas = int(c.fotoperiodo.split("/")[0])
        except (ValueError, IndexError):
            continue
        total += watts / 1000 * horas * max(0, (hasta - desde).days)
    return total


def cifras(cultivo):
    """Lo que se compara entre cultivos. Más liviano que el reporte completo."""
    fin, dias, veg, flora = _fechas(cultivo)
    plantas = list(cultivo.plantas.filter(archivado=False).exclude(estado="descartada"))
    seco = sum(p.yield_real_g or 0 for p in plantas)
    watts = cultivo.lampara_watts_reales
    return {
        "cultivo": cultivo, "fin": fin, "dias": dias, "dias_veg": veg, "dias_flora": flora,
        "plantas": plantas, "seco": seco, "estimado": sum(p.yield_estimado_g or 0 for p in plantas),
        "g_por_watt": round(seco / float(watts), 2) if seco and watts else None,
        "g_por_planta": round(seco / len([p for p in plantas if p.yield_real_g])) if seco else None,
        "en_rango": _en_rango(cultivo, list(cultivo.mediciones.order_by("timestamp")))["total"],
        "energia": _energia(cultivo, fin, seco),
    }


def anteriores(cultivo):
    """Otros cultivos cerrados del mismo dueño, del más nuevo al más viejo."""
    if not cultivo.propietario_id:
        return []
    otros = (Cultivo.objects.filter(propietario_id=cultivo.propietario_id, estado="finalizado")
             .exclude(pk=cultivo.pk).order_by("-fecha_fin", "-fecha_inicio")[:ANTERIORES])
    parametros = {p.etapa: p for p in ParametroIdeal.objects.all()}
    lista = []
    for otro in otros.prefetch_related("cambios_etapa"):
        otro.__dict__["_parametro_por_etapa"] = parametros
        lista.append(cifras(otro))
    return lista


def reporte(cultivo):
    mediciones = list(cultivo.mediciones.order_by("timestamp"))
    datos = cifras(cultivo)
    plantas = datos["plantas"]
    en_rango = _en_rango(cultivo, mediciones)

    riegos = cultivo.riegos.aggregate(count=Count("id"), vol_total=Sum("volumen_total_ml"),
                                      ph_avg=Avg("ph_agua"), ec_avg=Avg("ec_solucion"))
    nutrientes = (
        NutrienteAplicado.objects.filter(riego__cultivo=cultivo)
        .values("nutriente__nombre", "nutriente__marca", "nutriente__unidad")
        .annotate(aplicaciones=Count("id"), dosis_avg=Avg("dosis_g_por_litro"),
                  total=Sum(ExpressionWrapper(F("dosis_g_por_litro") * F("riego__volumen_total_ml") / 1000.0,
                                              output_field=DecimalField(max_digits=12, decimal_places=2))))
        .order_by("nutriente__marca", "nutriente__nombre")
    )
    ambiente = None
    if mediciones:
        temps = [float(m.temperatura_c) for m in mediciones]
        hrs = [float(m.humedad_relativa) for m in mediciones]
        vpds = [m.vpd for m in mediciones]
        n = len(mediciones)
        ambiente = {"count": n, "temp_avg": sum(temps) / n, "temp_min": min(temps), "temp_max": max(temps),
                    "hr_avg": sum(hrs) / n, "hr_min": min(hrs), "hr_max": max(hrs),
                    "vpd_avg": sum(vpds) / n, "vpd_min": min(vpds), "vpd_max": max(vpds)}

    # Yield por planta: barras del estimado y del real en la misma escala.
    tope = max([p.yield_real_g or 0 for p in plantas] + [p.yield_estimado_g or 0 for p in plantas] + [1])
    yield_plantas = [{"planta": p,
                      "estimado_pct": round(100 * (p.yield_estimado_g or 0) / tope),
                      "real_pct": round(100 * (p.yield_real_g or 0) / tope)} for p in plantas]

    tipo_display = dict(Evento.TIPO_CHOICES)
    con_humedo = [p for p in plantas if p.peso_humedo_g and p.yield_real_g]
    humedo = sum(p.peso_humedo_g for p in con_humedo)
    return {
        **datos,
        "en_rango_detalle": en_rango, "barras_semanas": _barras_semanas(en_rango["semanas"]),
        "crecimiento": _crecimiento(cultivo, plantas),
        "yield_plantas": yield_plantas,
        "merma": round(100 * (1 - sum(p.yield_real_g for p in con_humedo) / humedo)) if humedo else None,
        "riegos": riegos, "litros": (riegos["vol_total"] or 0) / 1000, "nutrientes": nutrientes,
        "ambiente": ambiente,
        "eventos_por_tipo": [{"label": tipo_display.get(e["tipo"], e["tipo"]), "count": e["count"]}
                             for e in cultivo.eventos.values("tipo").annotate(count=Count("id")).order_by("-count")],
        "anteriores": anteriores(cultivo),
        "ancho": ANCHO, "alto": ALTO,
    }
