"""Tareas."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import Cultivo, Tarea
from ..permissions import cultivos_visibles, objeto_del_cultivo
from ..services.hoy import agrupar_tareas, item_tarea


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
    return render(request, plantilla, {"item": item_tarea(tarea, puede_editar=True, hoy=hoy), "hoy": hoy, "mostrar_categoria": True})


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


def _tareas(request, cultivos_qs, *, cultivo=None):
    categoria = request.GET.get("categoria", "")
    pendientes = Tarea.objects.filter(cultivo__in=cultivos_qs, completada=False).select_related("cultivo")
    hechas = Tarea.objects.filter(cultivo__in=cultivos_qs, completada=True).select_related("cultivo")
    if categoria:
        pendientes, hechas = pendientes.filter(categoria=categoria), hechas.filter(categoria=categoria)
    editables = set(cultivos_visibles(request.user, editar=True).values_list("pk", flat=True))
    hoy = timezone.localdate()
    grupos = agrupar_tareas(pendientes, hoy=hoy, editables=editables)
    hechas = [item_tarea(t, puede_editar=t.cultivo_id in editables, hoy=hoy)
              for t in hechas.order_by("-completada_en", "-pk")[:15]]
    return render(request, "growlog/tareas_list.html", {
        "cultivo": cultivo, "grupos": grupos, "hechas": hechas, "hoy": hoy,
        "pendientes_total": sum(len(g["items"]) for g in grupos),
        "categoria_filter": categoria, "categorias": Tarea.CATEGORIA_CHOICES,
        "puede_crear": bool(editables) and (cultivo is None or cultivo.pk in editables),
    })


@login_required
def tareas_list(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    return _tareas(request, Cultivo.objects.filter(pk=cultivo.pk), cultivo=cultivo)


@login_required
def tareas_todas(request):
    """Las tareas de todos los cultivos activos que podés ver."""
    activos = cultivos_visibles(request.user).filter(archivado=False).exclude(estado="finalizado")
    return _tareas(request, activos)
