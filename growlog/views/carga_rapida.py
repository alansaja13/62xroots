"""Carga rápida (HTMX) desde el detalle del cultivo."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django_htmx.http import HttpResponseClientRedirect

from ..forms import QuickECForm, QuickEntryForm, QuickEventoForm, QuickTareaForm
from ..models import Cultivo, Evento, MedicionAmbiente, MedicionEC, Tarea
from ..permissions import objeto_del_cultivo


@login_required
def quick_entry(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = QuickEntryForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        medicion = MedicionAmbiente.objects.create(
            cultivo=cultivo, temperatura_c=d["temperatura_c"],
            humedad_relativa=d["humedad_relativa"], notas=d.get("notas", ""),
            creado_por=request.user,
        )
        if d["rego"]:
            redirect_url = reverse("growlog:riego_crear", args=[cultivo.slug])
            if request.htmx:
                return HttpResponseClientRedirect(redirect_url)
            messages.success(request, "✓ Medición guardada — ahora elegí qué plantas regaste.")
            return redirect(redirect_url)
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"✓ Guardado — {medicion.temperatura_c}°C / {medicion.humedad_relativa}%HR / VPD {medicion.vpd} kPa")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return _render_quick(request, cultivo, "medicion", form)


def _render_quick(request, cultivo, tab, form):
    """Conserva la entrada y la pestaña activa al mostrar errores de registro."""
    context = {
        "form": QuickEntryForm(),
        "evento_form": QuickEventoForm(auto_id="id_evento_%s"),
        "tarea_form": QuickTareaForm(auto_id="id_tarea_%s"),
        "ec_form": QuickECForm(auto_id="id_ec_%s"),
        "cultivo": cultivo,
        "active_tab": tab,
    }
    key = {"medicion": "form", "evento": "evento_form", "tarea": "tarea_form", "ec": "ec_form"}[tab]
    context[key] = form
    return render(request, "growlog/quick.html", context)


@login_required
def quick_evento(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = QuickEventoForm(request.POST if request.method == "POST" else None, auto_id="id_evento_%s")
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        evento = Evento.objects.create(
            cultivo=cultivo, tipo=d["tipo"], descripcion=d["descripcion"],
            creado_por=request.user,
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"Evento «{evento.get_tipo_display()}» registrado.")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return _render_quick(request, cultivo, "evento", form)


@login_required
def quick_medicion_ec(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = QuickECForm(request.POST if request.method == "POST" else None, auto_id="id_ec_%s")
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        medicion = MedicionEC.objects.create(
            cultivo=cultivo, tipo=d["tipo"],
            ph=d.get("ph"), ec=d.get("ec"), temp_agua=d.get("temp_agua"),
            notas=d.get("notas", ""), creado_por=request.user,
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"Medición EC/pH registrada — {medicion.get_tipo_display()}")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return _render_quick(request, cultivo, "ec", form)


@login_required
def quick_tarea(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = QuickTareaForm(request.POST if request.method == "POST" else None, auto_id="id_tarea_%s")
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        tarea = Tarea.objects.create(
            cultivo=cultivo, titulo=d["titulo"], categoria=d["categoria"],
            prioridad=d["prioridad"], fecha_objetivo=d.get("fecha_objetivo"),
            creado_por=request.user,
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"Tarea «{tarea.titulo}» creada.")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return _render_quick(request, cultivo, "tarea", form)
