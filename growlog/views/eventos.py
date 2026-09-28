"""Eventos."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..forms import EventoForm
from ..models import Evento
from ..permissions import objeto_del_cultivo


@login_required
def evento_editar(request, pk):
    evento = objeto_del_cultivo(request, Evento, editar=True, pk=pk)
    form = EventoForm(request.POST or None, instance=evento)
    form.fields["plantas_afectadas"].queryset = evento.cultivo.plantas.all()
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Evento actualizado.")
        return redirect("growlog:cultivo_detail", evento.cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar evento",
        "subtitle": evento.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[evento.cultivo.slug]),
        "delete_url": reverse("growlog:evento_eliminar", args=[pk]),
    })


@login_required
def evento_eliminar(request, pk):
    evento = objeto_del_cultivo(request, Evento, editar=True, pk=pk)
    cultivo = evento.cultivo
    if request.method == "POST":
        evento.delete()
        messages.success(request, "Evento eliminado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar evento", "object_name": str(evento),
        "back_url": reverse("growlog:evento_editar", args=[pk]),
    })


@login_required
@require_POST
def evento_resolver_followup(request, pk):
    evento = objeto_del_cultivo(request, Evento, editar=True, pk=pk)
    evento.follow_up_resuelto = True
    evento.save(update_fields=["follow_up_resuelto"])
    return HttpResponse("")


# ---------------------------------------------------------------------------
