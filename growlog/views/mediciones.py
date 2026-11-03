"""Cambios de fotoperiodo."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import CambioFotoperiodoForm
from ..models import CambioFotoperiodo, Cultivo
from ..permissions import objeto_del_cultivo
from ..utils import get_cambio_fotoperiodo_activo


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
        # El vigente hoy, no el último cargado (que puede tener fecha futura).
        "activo": get_cambio_fotoperiodo_activo(cultivo, timezone.now()),
        "hoy": timezone.localdate(),
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
        "title": "Corregir fotoperíodo", "subtitle": cultivo.nombre,
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
        "title": "Eliminar fotoperíodo",
        "object_name": f"{cambio.fotoperiodo} · desde el {cambio.fecha_inicio:%d/%m/%Y}",
        "back_url": reverse("growlog:cambio_fotoperiodo_editar", args=[pk]),
    })
