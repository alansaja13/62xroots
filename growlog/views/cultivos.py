"""Hoy, detalle del cultivo, tendencias, timeline y ciclo de vida del cultivo."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import CambioEtapaCultivoForm, NuevoCultivoForm
from ..models import CambioEtapaCultivo, CambioEtapaPlanta, Cultivo, ParametroIdeal
from ..permissions import objeto_del_cultivo
from ..services.etapas import cambiar_etapa, reabrir_cultivo, sincronizar_cultivo
from ..services.hoy import resumen_hoy
from ..utils import (
    calcular_luz_estado,
    etapa_efectiva_cultivo,
    etapa_efectiva_planta,
    get_cambio_fotoperiodo_activo,
    get_etapa_activa_cultivo,
    get_flip_a_flora,
    rango_vpd_en,
)
from .helpers import build_timeline, evaluar_ambiente


@login_required
def dashboard(request):
    return render(request, "growlog/dashboard.html", resumen_hoy(request.user))


@login_required
def cultivo_detail(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    ultima_medicion = cultivo.mediciones.first()
    ultima_medicion_ec = cultivo.mediciones_ec.first()
    tareas_pendientes = cultivo.tareas.filter(completada=False).order_by("fecha_objetivo", "-prioridad")[:10]
    tareas_completadas = cultivo.tareas.filter(completada=True).order_by("-completada_en")[:5]
    ultimos_registros = build_timeline(cultivo, limit=8)
    plantas_count = cultivo.plantas.activas().count()
    plantas = list(cultivo.plantas.filter(archivado=False).prefetch_related("cambios_etapa"))
    etapa_display_map = dict(CambioEtapaPlanta.ETAPA_CHOICES)
    for p in plantas:
        p.etapa_actual = etapa_efectiva_planta(p)
        p.etapa_actual_display = etapa_display_map.get(p.etapa_actual)
    semaforo = None
    if ultima_medicion:
        # Misma etapa que usa vpd_estado en el timeline: la vigente cuando se midió.
        etapa = etapa_efectiva_cultivo(cultivo, timezone.localdate(ultima_medicion.timestamp))
        if etapa:
            try:
                param = ParametroIdeal.objects.get(etapa=etapa)
                semaforo = evaluar_ambiente(ultima_medicion, param)
            except ParametroIdeal.DoesNotExist:
                pass
    finalizado = cultivo.estado == "finalizado"
    fotoperiodo_activo = get_cambio_fotoperiodo_activo(cultivo, timezone.now())
    luz_estado_actual = None
    # La luz "ahora" no describe un cultivo cerrado.
    if fotoperiodo_activo and not finalizado:
        luz_estado_actual = calcular_luz_estado(
            timezone.now(), fotoperiodo_activo.hora_lights_on, fotoperiodo_activo.fotoperiodo
        )
    progreso = None
    if cultivo.dias_veg_estimados and cultivo.dias_flora_estimados:
        total = cultivo.dias_veg_estimados + cultivo.dias_flora_estimados
        dias = cultivo.dias_desde_inicio
        pct = min(100, round(dias / total * 100))
        veg_pct = round(cultivo.dias_veg_estimados / total * 100, 2)
        progreso = {
            "pct": pct,
            "total": total,
            "dias": dias,
            "veg_pct": veg_pct,
            "en_flora": dias >= cultivo.dias_veg_estimados,
            "dias_veg": cultivo.dias_veg_estimados,
            "dias_flora": cultivo.dias_flora_estimados,
        }
    etapa_cultivo = etapa_efectiva_cultivo(cultivo)
    hoy = timezone.localdate()
    followups_pendientes = cultivo.eventos.filter(
        follow_up_fecha__isnull=False,
        follow_up_resuelto=False,
    ).order_by("follow_up_fecha")
    # Día de flora: desde fecha_inicio_flora (marcada explícitamente), con
    # fallback al primer CambioFotoperiodo a ≤12h de luz para cultivos viejos
    # que aún no usaron la acción de marcar el flip.
    dia_flora = cultivo.dia_flora
    if dia_flora is None:
        flip = get_flip_a_flora(cultivo)
        referencia = cultivo.fecha_referencia
        if flip and flip.fecha_inicio <= referencia:
            dia_flora = (referencia - flip.fecha_inicio).days + 1
    # Días desde el último riego
    ultimo_riego = cultivo.riegos.first()
    dias_sin_riego = None
    if ultimo_riego and not finalizado:
        dias_sin_riego = (hoy - timezone.localtime(ultimo_riego.timestamp).date()).days
    return render(request, "growlog/cultivo_detail.html", {
        "cultivo": cultivo, "ultima_medicion": ultima_medicion,
        "tareas_pendientes": tareas_pendientes, "tareas_completadas": tareas_completadas,
        "ultimos_registros": ultimos_registros,
        "semaforo": semaforo, "plantas_count": plantas_count, "plantas": plantas,
        "fotoperiodo_activo": fotoperiodo_activo,
        "luz_estado_actual": luz_estado_actual,
        "progreso": progreso,
        "followups_pendientes": followups_pendientes,
        "hoy": hoy,
        "ultima_medicion_ec": ultima_medicion_ec,
        "dia_flora": dia_flora,
        "etapa_actual": etapa_cultivo,
        "etapa_actual_display": etapa_display_map.get(etapa_cultivo),
        "dias_sin_riego": dias_sin_riego,
    })


@login_required
def cultivo_tendencias(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    return render(request, "growlog/tendencias.html", {"cultivo": cultivo})


@login_required
def cultivo_tendencias_json(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    try:
        dias = int(request.GET.get("dias", 30))
    except ValueError:
        dias = 30
    dias = max(0, min(dias, 3650))  # 0 = todo; un valor enorme desbordaría timedelta

    mediciones_qs = cultivo.mediciones.order_by("timestamp")
    if dias > 0:
        desde = timezone.now() - timedelta(days=dias)
        mediciones_qs = mediciones_qs.filter(timestamp__gte=desde)

    mediciones = [{
        "timestamp": m.timestamp.isoformat(),
        "temp": float(m.temperatura_c),
        "hr": float(m.humedad_relativa),
        "vpd": m.vpd,
        "vpd_estado": m.vpd_estado,
        "vpd_rango": rango_vpd_en(cultivo, timezone.localdate(m.timestamp)),
        "luz_estado": m.luz_estado,
    } for m in mediciones_qs]

    rango_ideal = None
    etapa = etapa_efectiva_cultivo(cultivo)
    if etapa:
        param = ParametroIdeal.objects.filter(etapa=etapa).first()
        if param:
            rango_ideal = {
                "temp_min": float(param.temp_min), "temp_max": float(param.temp_max),
                "hr_min": float(param.hr_min), "hr_max": float(param.hr_max),
                "vpd_min": float(param.vpd_min), "vpd_max": float(param.vpd_max),
            }

    return JsonResponse({"mediciones": mediciones, "rango_ideal": rango_ideal})


@login_required
def timeline(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    tipo = request.GET.get("tipo", "")
    todos = build_timeline(cultivo, limit=200)
    VALID_TIPOS = {"medicion", "riego", "evento", "medicion_ec"}
    if tipo in VALID_TIPOS:
        registros = [r for r in todos if r["tipo"] == tipo]
    else:
        tipo = ""
        registros = todos
    counts = {t: sum(1 for r in todos if r["tipo"] == t) for t in VALID_TIPOS}
    return render(request, "growlog/timeline.html", {
        "cultivo": cultivo,
        "registros": registros,
        "tipo_activo": tipo,
        "counts": counts,
        "total": len(todos),
    })


@login_required
def nuevo_cultivo(request):
    form = NuevoCultivoForm(request.POST or None, initial={"fecha_inicio": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        cultivo = form.save(commit=False)
        cultivo.creado_por = request.user
        cultivo.propietario = request.user
        cultivo.save()
        cambiar_etapa(cultivo, form.cleaned_data["etapa_inicial"] or "veg_temprano", cultivo.fecha_inicio)
        messages.success(request, f"Cultivo «{cultivo.nombre}» creado. ¡A cultivar!")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/nuevo_cultivo.html", {"form": form})


@login_required
def cultivo_editar(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = NuevoCultivoForm(request.POST or None, instance=cultivo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cultivo actualizado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar — {cultivo.nombre}",
        "subtitle": f"Día {cultivo.dias_desde_inicio}",
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
def cultivo_marcar_flora(request, slug):
    """Atajo al cambio a flora. Si el cultivo ya entró en flora no hace nada:
    el contador nunca se reinicia desde acá."""
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    if request.method == "POST":
        if cultivo.fecha_inicio_flora:
            messages.info(request, f"Ya está en flora desde el {cultivo.fecha_inicio_flora:%d/%m/%Y}. "
                                   "Para corregirlo, editá la etapa en el historial.")
        else:
            cambiar_etapa(cultivo, "flora_temprana", timezone.localdate())
            messages.success(request, "Cambio a flora marcado hoy.")
    return redirect("growlog:cultivo_detail", cultivo.slug)


@login_required
def cultivo_etapa(request, slug):
    """Etapa del cultivo: cambiarla y ver el historial."""
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    puede_editar = request.puede_editar_cultivo
    etapa_actual = etapa_efectiva_cultivo(cultivo)
    vigente = get_etapa_activa_cultivo(cultivo)
    form = None
    if puede_editar:
        form = CambioEtapaCultivoForm(request.POST or None, initial={
            "fecha_inicio": timezone.localdate(), "etapa": etapa_actual})
        if request.method == "POST" and form.is_valid():
            cambiar_etapa(cultivo, form.cleaned_data["etapa"], form.cleaned_data["fecha_inicio"],
                          form.cleaned_data["notas"])
            messages.success(request, f"Etapa {dict(CambioEtapaCultivo.ETAPA_CHOICES)[form.cleaned_data['etapa']]} guardada.")
            return redirect("growlog:cultivo_etapa", cultivo.slug)
    return render(request, "growlog/etapa_historial.html", {
        "cultivo": cultivo, "form": form, "puede_editar": puede_editar,
        "historial": cultivo.cambios_etapa.all(), "vigente_pk": vigente.pk if vigente else None,
        "etapa_actual": etapa_actual,
        "etapa_actual_display": dict(CambioEtapaCultivo.ETAPA_CHOICES).get(etapa_actual),
        "dia_flora": cultivo.dia_flora,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
        "back_label": cultivo.nombre,
        "editar_url": "growlog:cambio_etapa_cultivo_editar",
        "eliminar_url": "growlog:cambio_etapa_cultivo_eliminar",
    })


@login_required
def cambio_etapa_cultivo_editar(request, pk):
    cambio = objeto_del_cultivo(request, CambioEtapaCultivo, editar=True, pk=pk)
    cultivo = cambio.cultivo
    form = CambioEtapaCultivoForm(request.POST or None, instance=cambio)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.full_clean()
            obj.save()
            sincronizar_cultivo(cultivo)
            messages.success(request, "Etapa actualizada.")
            return redirect("growlog:cultivo_etapa", cultivo.slug)
        except ValidationError as e:
            for mensaje in e.messages:
                form.add_error(None, mensaje)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar etapa — {cultivo.nombre}",
        "back_url": reverse("growlog:cultivo_etapa", args=[cultivo.slug]),
        "delete_url": reverse("growlog:cambio_etapa_cultivo_eliminar", args=[pk]),
    })


@login_required
def cambio_etapa_cultivo_eliminar(request, pk):
    cambio = objeto_del_cultivo(request, CambioEtapaCultivo, editar=True, pk=pk)
    cultivo = cambio.cultivo
    if request.method == "POST":
        cambio.delete()
        sincronizar_cultivo(cultivo)
        messages.success(request, "Registro de etapa eliminado.")
        return redirect("growlog:cultivo_etapa", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": f"Eliminar etapa {cambio.get_etapa_display()}",
        "object_name": f"{cambio.get_etapa_display()} · desde {cambio.fecha_inicio}",
        "back_url": reverse("growlog:cambio_etapa_cultivo_editar", args=[pk]),
    })


@login_required
def cultivo_finalizar(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    if request.method == "POST":
        cultivo.estado = "finalizado"
        if not cultivo.fecha_fin:
            cultivo.fecha_fin = timezone.localdate()
        cultivo.save()
        messages.success(request, f"Cultivo «{cultivo.nombre}» finalizado.")
    return redirect("growlog:cultivo_detail", cultivo.slug)


@login_required
def cultivo_reabrir(request, slug):
    """Deshace finalizar, por si se tocó sin querer o el ciclo siguió."""
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    if request.method == "POST":
        if cultivo.estado == "finalizado":
            reabrir_cultivo(cultivo)
            messages.success(request, f"Cultivo «{cultivo.nombre}» reabierto. Revisá la etapa si no es la correcta.")
        else:
            messages.info(request, "Este cultivo no estaba finalizado.")
    return redirect("growlog:cultivo_detail", cultivo.slug)


@login_required
def registrar_en_cultivo(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    return redirect(f"{reverse('growlog:registrar')}?cultivo={cultivo.pk}")
