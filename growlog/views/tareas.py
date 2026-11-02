"""Tareas."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import TareaForm
from ..models import Cultivo, Tarea
from ..permissions import objeto_del_cultivo
from ..services.hoy import item_tarea


@login_required
def tarea_editar(request, pk):
    tarea = objeto_del_cultivo(request, Tarea, editar=True, pk=pk)
    estaba_completada = tarea.completada
    form = TareaForm(request.POST or None, instance=tarea)
    if request.method == "POST" and form.is_valid():
        tarea = form.save(commit=False)
        # Igual que completar/descompletar: la fecha acompaña al estado.
        if tarea.completada and not estaba_completada:
            tarea.completada_en = timezone.now()
        elif not tarea.completada:
            tarea.completada_en = None
        tarea.save()
        messages.success(request, "Tarea actualizada.")
        return redirect("growlog:cultivo_detail", tarea.cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar tarea",
        "subtitle": tarea.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[tarea.cultivo.slug]),
        "delete_url": reverse("growlog:tarea_eliminar", args=[pk]),
    })


@login_required
def tarea_eliminar(request, pk):
    tarea = objeto_del_cultivo(request, Tarea, editar=True, pk=pk)
    cultivo = tarea.cultivo
    if request.method == "POST":
        tarea.delete()
        messages.success(request, "Tarea eliminada.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar tarea", "object_name": tarea.titulo,
        "back_url": reverse("growlog:tarea_editar", args=[pk]),
    })


def _fila_hoy(request, tarea, plantilla):
    hoy = timezone.localdate()
    return render(request, plantilla, {"item": item_tarea(tarea, puede_editar=True, hoy=hoy), "hoy": hoy})


@require_POST
@login_required
def tarea_completar(request, pk):
    tarea = objeto_del_cultivo(request, Tarea, editar=True, pk=pk)
    tarea.completada = True
    tarea.completada_en = timezone.now()
    tarea.save()
    if request.htmx:
        # La lista de tareas no tiene panel de completadas: solo se borra la fila.
        if request.POST.get("origen") == "lista":
            return HttpResponse("")
        if request.POST.get("origen") == "hoy":
            return _fila_hoy(request, tarea, "growlog/partials/hoy_tarea_hecha.html")
        return render(request, "growlog/partials/tarea_completar_oob.html", {"tarea": tarea})
    return redirect("growlog:cultivo_detail", tarea.cultivo.slug)


@require_POST
@login_required
def tarea_descompletar(request, pk):
    tarea = objeto_del_cultivo(request, Tarea, editar=True, pk=pk)
    tarea.completada = False
    tarea.completada_en = None
    tarea.save()
    if request.htmx and request.POST.get("origen") == "hoy":
        return _fila_hoy(request, tarea, "growlog/partials/hoy_item.html")
    if request.htmx:
        return render(request, "growlog/partials/tarea_descompletar_oob.html", {"tarea": tarea})
    return redirect("growlog:cultivo_detail", tarea.cultivo.slug)


@login_required
def tareas_list(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    qs = cultivo.tareas.all()
    categoria = request.GET.get("categoria", "")
    estado = request.GET.get("estado", "pendiente")
    if categoria:
        qs = qs.filter(categoria=categoria)
    if estado == "completada":
        qs = qs.filter(completada=True).order_by("-completada_en")
    elif estado == "todas":
        qs = qs.order_by("completada", "fecha_objetivo", "-prioridad")
    else:
        qs = qs.filter(completada=False).order_by("fecha_objetivo", "-prioridad")
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "growlog/tareas_list.html", {
        "cultivo": cultivo,
        "page_obj": page_obj,
        "categoria_filter": categoria,
        "estado_filter": estado,
        "categorias": Tarea.CATEGORIA_CHOICES,
        "today": timezone.localdate(),
    })
