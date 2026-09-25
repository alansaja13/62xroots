"""Mediciones de EC/pH y cambios de fotoperiodo."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import CambioFotoperiodoForm, DT_FMT, MedicionECForm
from ..models import CambioFotoperiodo, Cultivo, MedicionEC
from ..permissions import objeto_del_cultivo


# ---------------------------------------------------------------------------
# MedicionEC CRUD
# ---------------------------------------------------------------------------

@login_required
def medicion_ec_crear(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    initial = {"timestamp": timezone.localtime().strftime(DT_FMT)}
    form = MedicionECForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.cultivo = cultivo
        m.creado_por = request.user
        m.save()
        messages.success(request, "Medición EC/pH registrada.")
        return redirect("growlog:cultivo_detail", slug=slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva medición EC/pH",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[slug]),
    })


@login_required
def medicion_ec_editar(request, pk):
    medicion = objeto_del_cultivo(request, MedicionEC, editar=True, pk=pk)
    form = MedicionECForm(request.POST or None, instance=medicion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Medición EC/pH actualizada.")
        return redirect("growlog:medicion_ec_editar", pk=pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar medición EC/pH",
        "subtitle": medicion.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[medicion.cultivo.slug]),
        "delete_url": reverse("growlog:medicion_ec_eliminar", args=[pk]),
    })


@login_required
def medicion_ec_eliminar(request, pk):
    medicion = objeto_del_cultivo(request, MedicionEC, editar=True, pk=pk)
    cultivo = medicion.cultivo
    if request.method == "POST":
        medicion.delete()
        messages.success(request, "Medición EC/pH eliminada.")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar medición EC/pH", "object_name": str(medicion),
        "back_url": reverse("growlog:medicion_ec_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# CambioFotoperiodo
# ---------------------------------------------------------------------------

@login_required
def fotoperiodo_list(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    historial = cultivo.cambios_fotoperiodo.order_by("-fecha_inicio")

    if request.method == "POST":
        form = CambioFotoperiodoForm(request.POST)
        if form.is_valid():
            cambio = form.save(commit=False)
            cambio.cultivo = cultivo
            try:
                cambio.full_clean()
                cambio.save()
                messages.success(request, f"Fotoperiodo {cambio.fotoperiodo} guardado.")
                return redirect("growlog:fotoperiodo_list", slug=slug)
            except ValidationError as e:
                for mensaje in e.messages:
                    form.add_error(None, mensaje)
    else:
        form = CambioFotoperiodoForm(initial={"fecha_inicio": timezone.localdate()})

    return render(request, "growlog/fotoperiodo.html", {
        "cultivo": cultivo,
        "historial": historial,
        "form": form,
    })


@login_required
def cambio_fotoperiodo_editar(request, pk):
    cambio = objeto_del_cultivo(request, CambioFotoperiodo, editar=True, pk=pk)
    cultivo = cambio.cultivo
    form = CambioFotoperiodoForm(request.POST or None, instance=cambio)
    if form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.full_clean()
            obj.save()
            messages.success(request, "Fotoperiodo actualizado.")
            return redirect("growlog:fotoperiodo_list", slug=cultivo.slug)
        except ValidationError as e:
            for mensaje in e.messages:
                form.add_error(None, mensaje)
    return render(request, "growlog/crud_form.html", {
        "form": form,
        "title": f"Editar fotoperiodo — {cultivo.nombre}",
        "back_url": reverse("growlog:fotoperiodo_list", args=[cultivo.slug]),
        "delete_url": reverse("growlog:cambio_fotoperiodo_eliminar", args=[pk]),
    })


@login_required
def cambio_fotoperiodo_eliminar(request, pk):
    cambio = objeto_del_cultivo(request, CambioFotoperiodo, editar=True, pk=pk)
    cultivo = cambio.cultivo
    if request.method == "POST":
        cambio.delete()
        messages.success(request, "Registro de fotoperiodo eliminado.")
        return redirect("growlog:fotoperiodo_list", slug=cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": f"Eliminar fotoperiodo {cambio.fotoperiodo}",
        "object_name": f"{cambio.fotoperiodo} · desde {cambio.fecha_inicio}",
        "back_url": reverse("growlog:cambio_fotoperiodo_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
