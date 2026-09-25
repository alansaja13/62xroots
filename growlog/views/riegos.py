"""Riegos y nutrientes aplicados."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import DT_FMT, NutrienteAplicadoForm, riego_planta_entries, riego_planta_formset, RiegoForm
from ..models import Cultivo, NutrienteAplicado, Riego
from ..permissions import objeto_del_cultivo
from ..services.riegos import guardar_riego


# ---------------------------------------------------------------------------
# Riego CRUD
# ---------------------------------------------------------------------------

@login_required
def riego_crear(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    initial = {"timestamp": timezone.localtime().strftime(DT_FMT)}
    form = RiegoForm(request.POST or None, initial=initial)
    rp_formset, plantas = riego_planta_formset(cultivo, request.POST or None)

    if request.method == "POST" and form.is_valid() and rp_formset.is_valid():
        try:
            entries = riego_planta_entries(rp_formset, plantas)
            r = form.save(commit=False)
            r.cultivo = cultivo
            r.creado_por = request.user
            guardar_riego(riego=r, detalles=entries)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Riego registrado.")
            return redirect("growlog:riego_editar", pk=r.pk)

    return render(request, "growlog/riego_form.html", {
        "form": form, "riego": None,
        "rp_rows": list(zip(rp_formset.forms, plantas)),
        "rp_formset": rp_formset, "plantas": plantas,
        "title": "Nuevo riego",
        "subtitle": cultivo.nombre,
        "cultivo_slug": cultivo.slug,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
def riego_editar(request, pk):
    riego = objeto_del_cultivo(request, Riego, editar=True, pk=pk)
    cultivo = riego.cultivo
    form = RiegoForm(request.POST or None, instance=riego)
    rp_formset, plantas = riego_planta_formset(cultivo, request.POST or None, riego=riego)

    if request.method == "POST" and form.is_valid() and rp_formset.is_valid():
        try:
            entries = riego_planta_entries(rp_formset, plantas)
            r = form.save(commit=False)
            guardar_riego(riego=r, detalles=entries)
        except ValidationError as exc:
            form.add_error(None, exc.messages)
        else:
            messages.success(request, "Riego actualizado.")
            return redirect("growlog:riego_editar", pk=pk)

    nutrientes = riego.nutrientes_aplicados.select_related("nutriente").all()
    na_form = NutrienteAplicadoForm()
    return render(request, "growlog/riego_form.html", {
        "form": form, "riego": riego, "nutrientes": nutrientes,
        "na_form": na_form,
        "rp_rows": list(zip(rp_formset.forms, plantas)),
        "rp_formset": rp_formset, "plantas": plantas,
        "title": "Editar riego",
        "subtitle": cultivo.nombre,
        "cultivo_slug": cultivo.slug,
        "back_url": reverse("growlog:cultivo_detail", args=[riego.cultivo.slug]),
        "delete_url": reverse("growlog:riego_eliminar", args=[pk]),
    })


@login_required
def riego_eliminar(request, pk):
    riego = objeto_del_cultivo(request, Riego, editar=True, pk=pk)
    cultivo = riego.cultivo
    if request.method == "POST":
        riego.delete()
        messages.success(request, "Riego eliminado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar riego", "object_name": str(riego),
        "back_url": reverse("growlog:riego_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# NutrienteAplicado CRUD
# ---------------------------------------------------------------------------

@login_required
def nutriente_aplicado_crear(request, riego_pk):
    riego = objeto_del_cultivo(request, Riego, editar=True, pk=riego_pk)
    form = NutrienteAplicadoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        na = form.save(commit=False)
        na.riego = riego
        na.save()
        messages.success(request, "Nutriente agregado.")
        return redirect("growlog:riego_editar", pk=riego_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Agregar nutriente",
        "subtitle": str(riego),
        "back_url": reverse("growlog:riego_editar", args=[riego_pk]),
    })


@require_POST
@login_required
def nutriente_aplicado_eliminar(request, pk):
    na = objeto_del_cultivo(request, NutrienteAplicado, editar=True, pk=pk)
    riego_pk = na.riego_id
    na.delete()
    messages.success(request, "Nutriente eliminado.")
    return redirect("growlog:riego_editar", pk=riego_pk)


# ---------------------------------------------------------------------------
