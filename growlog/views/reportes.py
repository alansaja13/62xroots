"""Reporte de cosecha y módulo de energía."""
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from ..models import Cultivo, Evento, LecturaMedidor, NutrienteAplicado
from ..permissions import objeto_del_cultivo, tarifas_del_cultivo
from ..services.energia import calcular_meses, ciclo_activo
from ..utils import get_flip_a_flora


# ---------------------------------------------------------------------------
# Reporte de cultivo
# ---------------------------------------------------------------------------

def _reporte_csv(cultivo):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{cultivo.slug}-registros.csv"'
    resp.write("\ufeff")  # BOM para que Excel detecte UTF-8
    w = csv.writer(resp, delimiter=";")
    w.writerow(["fecha", "hora", "tipo", "dato", "ph", "ec", "volumen_ml",
                "temperatura_c", "humedad_pct", "vpd_kpa", "notas"])

    filas = []
    for m in cultivo.mediciones.all():
        ts = timezone.localtime(m.timestamp)
        filas.append((ts, [ts.date(), ts.strftime("%H:%M"), "medicion", "",
                           "", "", "", m.temperatura_c, m.humedad_relativa, m.vpd, m.notas]))
    for r in cultivo.riegos.all():
        ts = timezone.localtime(r.timestamp)
        nutris = " + ".join(
            f"{na.nutriente} {na.dosis_g_por_litro}g/L"
            for na in r.nutrientes_aplicados.select_related("nutriente")
        )
        notas = f"{nutris} | {r.notas}".strip(" |") if nutris else r.notas
        filas.append((ts, [ts.date(), ts.strftime("%H:%M"), "riego", "",
                           r.ph_agua or "", r.ec_solucion or "", r.volumen_total_ml,
                           "", "", "", notas]))
    for ec in cultivo.mediciones_ec.all():
        ts = timezone.localtime(ec.timestamp)
        filas.append((ts, [ts.date(), ts.strftime("%H:%M"), "medicion_ec", ec.get_tipo_display(),
                           ec.ph or "", ec.ec or "", "", "", "", "", ec.notas]))
    for e in cultivo.eventos.all():
        ts = timezone.localtime(e.timestamp)
        filas.append((ts, [ts.date(), ts.strftime("%H:%M"), "evento", e.get_tipo_display(),
                           "", "", "", "", "", "", e.descripcion]))

    filas.sort(key=lambda x: x[0])
    for _, row in filas:
        w.writerow(row)
    return resp


@login_required
def cultivo_reporte(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    if request.GET.get("export") == "csv":
        return _reporte_csv(cultivo)

    hoy = timezone.localdate()
    fecha_fin = cultivo.fecha_fin or hoy
    dias_totales = (fecha_fin - cultivo.fecha_inicio).days

    flip_fecha = cultivo.fecha_inicio_flora
    if not flip_fecha:
        flip = get_flip_a_flora(cultivo)
        flip_fecha = flip.fecha_inicio if flip else None
    dias_veg = dias_flora = None
    if flip_fecha and flip_fecha >= cultivo.fecha_inicio:
        dias_veg = (flip_fecha - cultivo.fecha_inicio).days
        dias_flora = max(0, (fecha_fin - flip_fecha).days)

    riego_stats = cultivo.riegos.aggregate(
        count=Count("id"),
        vol_total=Sum("volumen_total_ml"),
        ph_avg=Avg("ph_agua"),
        ec_avg=Avg("ec_solucion"),
    )
    litros_totales = (riego_stats["vol_total"] or 0) / 1000

    nutrientes = (
        NutrienteAplicado.objects
        .filter(riego__cultivo=cultivo)
        .values("nutriente__nombre", "nutriente__marca")
        .annotate(
            aplicaciones=Count("id"),
            dosis_avg=Avg("dosis_g_por_litro"),
            gramos_totales=Sum(ExpressionWrapper(
                F("dosis_g_por_litro") * F("riego__volumen_total_ml") / 1000.0,
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )),
        )
        .order_by("nutriente__marca", "nutriente__nombre")
    )

    mediciones = list(cultivo.mediciones.all())
    ambiente = None
    if mediciones:
        temps = [float(m.temperatura_c) for m in mediciones]
        hrs = [float(m.humedad_relativa) for m in mediciones]
        vpds = [m.vpd for m in mediciones]
        n = len(mediciones)
        ambiente = {
            "count": n,
            "temp_avg": sum(temps) / n, "temp_min": min(temps), "temp_max": max(temps),
            "hr_avg": sum(hrs) / n, "hr_min": min(hrs), "hr_max": max(hrs),
            "vpd_avg": sum(vpds) / n, "vpd_min": min(vpds), "vpd_max": max(vpds),
        }

    plantas = list(cultivo.plantas.all())
    yield_est_total = sum(p.yield_estimado_g or 0 for p in plantas)
    yield_real_total = sum(p.yield_real_g or 0 for p in plantas)
    g_por_watt = None
    if yield_real_total and cultivo.lampara_watts_reales:
        g_por_watt = round(yield_real_total / cultivo.lampara_watts_reales, 2)

    tipo_display = dict(Evento.TIPO_CHOICES)
    eventos_por_tipo = [
        {"label": tipo_display.get(e["tipo"], e["tipo"]), "count": e["count"]}
        for e in cultivo.eventos.values("tipo").annotate(count=Count("id")).order_by("-count")
    ]

    return render(request, "growlog/reporte.html", {
        "cultivo": cultivo,
        "dias_totales": dias_totales,
        "dias_veg": dias_veg,
        "dias_flora": dias_flora,
        "riego_stats": riego_stats,
        "litros_totales": litros_totales,
        "nutrientes": nutrientes,
        "ambiente": ambiente,
        "plantas": plantas,
        "yield_est_total": yield_est_total,
        "yield_real_total": yield_real_total,
        "g_por_watt": g_por_watt,
        "eventos_por_tipo": eventos_por_tipo,
        "eventos_total": cultivo.eventos.count(),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Energía
# ---------------------------------------------------------------------------

@login_required
def cultivo_energia(request, slug):
    from decimal import Decimal, InvalidOperation
    from datetime import date

    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    hoy = timezone.localdate()

    if request.method == "POST":
        fecha_str = request.POST.get("fecha", "").strip()
        kwh_str = request.POST.get("kwh_real", "").strip()
        notas = request.POST.get("notas", "").strip()
        try:
            fecha = date.fromisoformat(fecha_str)
        except ValueError:
            messages.error(request, "Fecha inválida.")
            return redirect("growlog:energia", slug=slug)
        try:
            kwh_real = Decimal(kwh_str.replace(",", "."))
            if kwh_real < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, "kWh inválido.")
            return redirect("growlog:energia", slug=slug)
        LecturaMedidor.objects.create(
            cultivo=cultivo, fecha=fecha, kwh_real=kwh_real, notas=notas[:500],
        )
        messages.success(request, "Lectura cargada.")
        return redirect("growlog:energia", slug=slug)

    tarifa = tarifas_del_cultivo(cultivo).filter(fecha_desde__lte=hoy).order_by("-fecha_desde").first()
    precio_kwh = float(tarifa.precio_kwh) if tarifa else 0

    costos_actuales = list(
        cultivo.costos_energeticos.select_related("equipo").filter(fecha_hasta__isnull=True)
    )
    todos_costos = list(
        cultivo.costos_energeticos.select_related("equipo").order_by("fecha_desde")
    )
    tarifas = list(tarifas_del_cultivo(cultivo).filter(fecha_desde__lte=hoy).order_by("-fecha_desde"))

    equipos_rows = []
    total_kwh_mes = 0.0
    total_costo_mes = 0.0
    for ce in costos_actuales:
        kwh = ce.equipo.kwh_mes
        costo = round(kwh * precio_kwh, 0)
        total_kwh_mes += kwh
        total_costo_mes += costo
        equipos_rows.append({"equipo": ce.equipo, "kwh_mes": kwh, "costo_mes": int(costo)})

    meses = calcular_meses(cultivo.fecha_inicio, todos_costos, tarifas, hoy)
    kwh_acumulado = round(sum(m["kwh_estimado"] for m in meses), 1)
    costo_acumulado = int(round(sum(m["costo_estimado"] for m in meses), 0))

    yield_total = sum(
        p.yield_estimado_g for p in cultivo.plantas.filter(archivado=False) if p.yield_estimado_g
    )
    costo_por_gramo = int(round(costo_acumulado / yield_total, 0)) if yield_total > 0 else None

    lecturas = list(cultivo.lecturas_medidor.all())
    kwh_real = None
    costo_real = None
    variacion_pct = None
    alerta = False
    if lecturas:
        kwh_real = round(float(sum(l.kwh_real for l in lecturas)), 1)
        costo_real = int(round(kwh_real * precio_kwh, 0))
        if kwh_acumulado > 0:
            variacion_pct = round((kwh_real - kwh_acumulado) / kwh_acumulado * 100, 1)
            alerta = kwh_real > kwh_acumulado * 1.15

    return render(request, "growlog/energia.html", {
        "cultivo": cultivo,
        "tarifa": tarifa,
        "ciclo": ciclo_activo(cultivo, hoy),
        "equipos_rows": equipos_rows,
        "total_kwh_mes": round(total_kwh_mes, 1),
        "total_costo_mes": int(total_costo_mes),
        "kwh_acumulado": kwh_acumulado,
        "costo_acumulado": costo_acumulado,
        "costo_por_gramo": costo_por_gramo,
        "meses": meses,
        "lecturas": lecturas,
        "kwh_real": kwh_real,
        "costo_real": costo_real,
        "variacion_pct": variacion_pct,
        "alerta": alerta,
        "hoy": hoy,
    })


# ---------------------------------------------------------------------------
