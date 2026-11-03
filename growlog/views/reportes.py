"""Reporte de cosecha y módulo de energía."""
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import CostoEnergetico, Cultivo, Equipo, LecturaMedidor, TarifaElectrica
from ..permissions import equipos_asignables, objeto_del_cultivo, tarifas_del_cultivo
from ..services.energia import calcular_meses, ciclo_activo
from ..services.reporte import reporte


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
            f"{na.nutriente} {na.dosis_g_por_litro} {na.nutriente.get_unidad_display()}"
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
    return render(request, "growlog/reporte.html", reporte(cultivo))


# ---------------------------------------------------------------------------
# Energía
# ---------------------------------------------------------------------------

def _numero(valor, *, minimo=0, maximo=None):
    """Decimal de un campo del formulario (acepta coma), o None si no sirve."""
    try:
        n = Decimal((valor or "").strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not n.is_finite() or n < minimo or (maximo is not None and n > maximo):
        return None
    return n


def _fecha(valor, tope):
    try:
        fecha = date.fromisoformat((valor or "").strip())
    except ValueError:
        return None
    return fecha if fecha <= tope else None


def _accion_energia(request, cultivo, hoy):
    """Procesa un POST de la pantalla de energía. Devuelve el mensaje de error, o None si salió bien."""
    p = request.POST
    accion = p.get("accion", "lectura")
    if accion in ("lectura", "lectura_editar"):
        fecha, kwh = _fecha(p.get("fecha"), hoy), _numero(p.get("kwh_real"), maximo=Decimal("99999999"))
        if fecha is None:
            return "Fecha inválida."
        if kwh is None:
            return "kWh inválido."
        lectura = (get_object_or_404(cultivo.lecturas_medidor, pk=p.get("pk")) if accion == "lectura_editar"
                   else LecturaMedidor(cultivo=cultivo))
        lectura.fecha, lectura.kwh_real, lectura.notas = fecha, kwh, p.get("notas", "").strip()[:500]
        lectura.save()
        messages.success(request, "Lectura guardada." if accion == "lectura_editar" else "Lectura cargada.")
    elif accion == "lectura_borrar":
        get_object_or_404(cultivo.lecturas_medidor, pk=p.get("pk")).delete()
        messages.success(request, "Lectura borrada.")
    elif accion == "tarifa":
        if cultivo.propietario_id != request.user.pk:
            return "La tarifa la carga quien creó el cultivo."
        fecha = _fecha(p.get("fecha_desde"), hoy + timedelta(days=366))
        precio = _numero(p.get("precio_kwh"), maximo=Decimal("999999"))
        if fecha is None or not precio:
            return "Revisá el precio y la fecha de la tarifa."
        TarifaElectrica.objects.create(fecha_desde=fecha, precio_kwh=precio, propietario=request.user,
                                       distribuidora=p.get("distribuidora", "").strip()[:100] or "Sin especificar")
        messages.success(request, "Tarifa guardada.")
    elif accion == "equipo":
        tarifa = tarifas_del_cultivo(cultivo).filter(fecha_desde__lte=hoy).order_by("-fecha_desde").first()
        if tarifa is None:
            return "Primero cargá la tarifa de la luz."
        desde = _fecha(p.get("fecha_desde"), hoy)
        if desde is None:
            return "Fecha inválida."
        if p.get("equipo"):
            equipo = equipos_asignables(request.user, cultivo).filter(pk=p.get("equipo")).first()
            if equipo is None:
                return "Ese equipo no está disponible."
        else:
            watts, horas = _numero(p.get("watts"), maximo=Decimal("100000")), _numero(p.get("horas_dia"), maximo=24)
            nombre = p.get("nombre", "").strip()[:120]
            if not nombre or not watts or horas is None:
                return "Completá nombre, watts y horas por día del equipo."
            categoria = p.get("categoria") if p.get("categoria") in dict(Equipo.CATEGORIA_CHOICES) else "otro"
            equipo = Equipo.objects.create(nombre=nombre, watts=watts, horas_dia=horas, categoria=categoria,
                                           propietario=request.user)
        CostoEnergetico.objects.create(cultivo=cultivo, equipo=equipo, tarifa=tarifa, fecha_desde=desde)
        messages.success(request, f"{equipo.nombre} sumado al cultivo.")
    elif accion == "equipo_editar":
        costo = get_object_or_404(cultivo.costos_energeticos.select_related("equipo"), pk=p.get("pk"))
        watts, horas = _numero(p.get("watts"), maximo=Decimal("100000")), _numero(p.get("horas_dia"), maximo=24)
        if not watts or horas is None:
            return "Revisá los watts y las horas por día."
        equipo = costo.equipo
        equipo.watts, equipo.horas_dia = watts, horas
        equipo.save(update_fields=["watts", "horas_dia"])
        messages.success(request, f"{equipo.nombre} actualizado.")
    elif accion == "equipo_quitar":
        costo = get_object_or_404(cultivo.costos_energeticos, pk=p.get("pk"), fecha_hasta__isnull=True)
        costo.fecha_hasta = max(hoy, costo.fecha_desde)
        costo.save(update_fields=["fecha_hasta"])
        messages.success(request, "Equipo sacado del cultivo desde hoy. Lo que consumió hasta ahora sigue en la cuenta.")
    return None


@login_required
def cultivo_energia(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    hoy = timezone.localdate()
    if request.method == "POST":
        error = _accion_energia(request, cultivo, hoy)
        if error:
            messages.error(request, error)
        return redirect("growlog:energia", slug=slug)

    tarifas = list(tarifas_del_cultivo(cultivo).filter(fecha_desde__lte=hoy).order_by("-fecha_desde"))
    tarifa = tarifas[0] if tarifas else None
    precio_kwh = float(tarifa.precio_kwh) if tarifa else 0
    todos_costos = list(cultivo.costos_energeticos.select_related("equipo").order_by("fecha_desde"))
    activos = [c for c in todos_costos if c.fecha_hasta is None]
    equipos_rows = [{"costo": c, "equipo": c.equipo, "kwh_mes": c.equipo.kwh_mes,
                     "costo_mes": round(c.equipo.kwh_mes * precio_kwh)} for c in activos]
    meses = calcular_meses(cultivo.fecha_inicio, todos_costos, tarifas, hoy)
    kwh_acumulado = round(sum(m["kwh_estimado"] for m in meses), 1)
    lecturas = list(cultivo.lecturas_medidor.all())
    kwh_real = round(float(sum(l.kwh_real for l in lecturas)), 1) if lecturas else None
    variacion = round((kwh_real - kwh_acumulado) / kwh_acumulado * 100, 1) if lecturas and kwh_acumulado else None
    en_uso = {c.equipo_id for c in activos}
    return render(request, "growlog/energia.html", {
        "cultivo": cultivo, "hoy": hoy, "tarifa": tarifa,
        "ciclo": ciclo_activo(cultivo, hoy),
        "equipos_rows": equipos_rows,
        "total_kwh_mes": round(sum(r["kwh_mes"] for r in equipos_rows), 1),
        "total_costo_mes": sum(r["costo_mes"] for r in equipos_rows),
        "kwh_acumulado": kwh_acumulado,
        "costo_acumulado": round(sum(m["costo_estimado"] for m in meses)),
        "meses": meses, "lecturas": lecturas, "kwh_real": kwh_real,
        "costo_real": round(kwh_real * precio_kwh) if kwh_real is not None and tarifa else None,
        "variacion_pct": variacion, "alerta": bool(variacion and variacion > 15),
        "equipos_disponibles": [e for e in equipos_asignables(request.user, cultivo) if e.pk not in en_uso],
        "categorias": Equipo.CATEGORIA_CHOICES,
        "es_duenio": cultivo.propietario_id == request.user.pk,
    })
