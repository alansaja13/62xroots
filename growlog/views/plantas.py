"""Plantas, sus mediciones y cambios de etapa."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import CambioEtapaPlantaForm, MedicionPlantaForm, PlantaForm
from ..models import CambioEtapaPlanta, Cultivo, MedicionPlanta, Planta
from ..permissions import objeto_del_cultivo
from ..utils import etapa_efectiva_planta


# ---------------------------------------------------------------------------
# Planta CRUD
# ---------------------------------------------------------------------------

@login_required
def planta_crear(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = PlantaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.cultivo = cultivo
        p.creado_por = request.user
        p.save()
        messages.success(request, f"Planta «{p.apodo}» creada.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva planta",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
def planta_editar(request, pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=pk)
    form = PlantaForm(request.POST or None, instance=planta)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Planta actualizada.")
        return redirect("growlog:planta_detail", pk=pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar — {planta.apodo}",
        "subtitle": planta.cultivo.nombre,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
        "delete_url": reverse("growlog:planta_eliminar", args=[pk]),
    })


@login_required
def planta_eliminar(request, pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=pk)
    cultivo = planta.cultivo
    if request.method == "POST":
        nombre = planta.apodo
        if planta.eliminar_o_archivar():
            messages.success(request, f"Planta «{nombre}» eliminada.")
        else:
            messages.success(request, f"Planta «{nombre}» archivada. Sus riegos, mediciones y etapas se conservan; "
                                      "podés restaurarla editándola.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    if planta.tiene_historial():
        return render(request, "growlog/crud_delete.html", {
            "title": "Archivar planta", "object_name": planta.apodo,
            "warn": "tiene historial: se archiva y se conservan sus riegos, fotos y etapas",
            "confirm_label": "archivar planta", "confirm_icon": "bi-archive",
            "back_url": reverse("growlog:planta_detail", args=[pk]),
        })
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar planta", "object_name": planta.apodo,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
    })


@login_required
def planta_detail(request, pk):
    planta = objeto_del_cultivo(request, Planta, pk=pk)
    mediciones = list(planta.mediciones.all())
    fotos = [m for m in mediciones if m.foto]
    riegos_planta = list(
        planta.riegos_detalle.select_related("riego").order_by("-riego__timestamp")[:20]
    )
    eventos = list(planta.eventos.order_by("-timestamp")[:20])
    etapa_actual = etapa_efectiva_planta(planta)
    return render(request, "growlog/planta_detail.html", {
        "planta": planta, "mediciones": mediciones,
        "fotos": fotos,
        "cultivo": planta.cultivo,
        "riegos_planta": riegos_planta,
        "eventos": eventos,
        "etapa_actual": etapa_actual,
        "etapa_actual_display": dict(CambioEtapaPlanta.ETAPA_CHOICES).get(etapa_actual),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# MedicionPlanta CRUD
# ---------------------------------------------------------------------------

@login_required
def medicion_planta_crear(request, planta_pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=planta_pk)
    form = MedicionPlantaForm(request.POST or None, request.FILES or None,
                              initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.planta = planta
        m.creado_por = request.user
        m.save()
        messages.success(request, "Medición registrada.")
        return redirect("growlog:planta_detail", pk=planta_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva medición de planta",
        "subtitle": str(planta),
        "back_url": reverse("growlog:planta_detail", args=[planta_pk]),
        "multipart": True,
    })


@login_required
def medicion_planta_editar(request, pk):
    medicion = objeto_del_cultivo(request, MedicionPlanta, editar=True, pk=pk)
    form = MedicionPlantaForm(request.POST or None, request.FILES or None, instance=medicion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Medición actualizada.")
        return redirect("growlog:planta_detail", pk=medicion.planta_id)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar medición",
        "subtitle": str(medicion.planta),
        "back_url": reverse("growlog:planta_detail", args=[medicion.planta_id]),
        "delete_url": reverse("growlog:medicion_planta_eliminar", args=[pk]),
        "multipart": True,
    })


@login_required
def medicion_planta_eliminar(request, pk):
    medicion = objeto_del_cultivo(request, MedicionPlanta, editar=True, pk=pk)
    planta_pk = medicion.planta_id
    if request.method == "POST":
        medicion.delete()
        messages.success(request, "Medición eliminada.")
        return redirect("growlog:planta_detail", pk=planta_pk)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar medición", "object_name": str(medicion),
        "back_url": reverse("growlog:planta_detail", args=[planta_pk]),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# CambioEtapaPlanta
# ---------------------------------------------------------------------------

@login_required
def planta_etapa_list(request, pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=pk)
    historial = planta.cambios_etapa.order_by("-fecha_inicio")

    if request.method == "POST":
        form = CambioEtapaPlantaForm(request.POST)
        if form.is_valid():
            cambio = form.save(commit=False)
            cambio.planta = planta
            try:
                cambio.full_clean()
                cambio.save()
                messages.success(request, f"Etapa {cambio.get_etapa_display()} guardada.")
                return redirect("growlog:planta_etapa_list", pk=pk)
            except ValidationError as e:
                for mensaje in e.messages:
                    form.add_error(None, mensaje)
    else:
        form = CambioEtapaPlantaForm(initial={"fecha_inicio": timezone.localdate()})

    return render(request, "growlog/etapa_planta.html", {
        "planta": planta,
        "cultivo": planta.cultivo,
        "historial": historial,
        "form": form,
    })


@login_required
def cambio_etapa_planta_editar(request, pk):
    cambio = objeto_del_cultivo(request, CambioEtapaPlanta, editar=True, pk=pk)
    planta = cambio.planta
    form = CambioEtapaPlantaForm(request.POST or None, instance=cambio)
    if form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.full_clean()
            obj.save()
            messages.success(request, "Etapa actualizada.")
            return redirect("growlog:planta_etapa_list", pk=planta.pk)
        except ValidationError as e:
            for mensaje in e.messages:
                form.add_error(None, mensaje)
    return render(request, "growlog/crud_form.html", {
        "form": form,
        "title": f"Editar etapa — {planta.apodo}",
        "back_url": reverse("growlog:planta_etapa_list", args=[planta.pk]),
        "delete_url": reverse("growlog:cambio_etapa_planta_eliminar", args=[pk]),
    })


@login_required
def cambio_etapa_planta_eliminar(request, pk):
    cambio = objeto_del_cultivo(request, CambioEtapaPlanta, editar=True, pk=pk)
    planta = cambio.planta
    if request.method == "POST":
        cambio.delete()
        messages.success(request, "Registro de etapa eliminado.")
        return redirect("growlog:planta_etapa_list", pk=planta.pk)
    return render(request, "growlog/crud_delete.html", {
        "title": f"Eliminar etapa {cambio.get_etapa_display()}",
        "object_name": f"{cambio.get_etapa_display()} · desde {cambio.fecha_inicio}",
        "back_url": reverse("growlog:cambio_etapa_planta_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
