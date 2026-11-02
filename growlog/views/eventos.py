"""Eventos."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from ..models import Evento
from ..permissions import objeto_del_cultivo


@login_required
@require_POST
def evento_resolver_followup(request, pk):
    evento = objeto_del_cultivo(request, Evento, editar=True, pk=pk)
    evento.follow_up_resuelto = True
    evento.save(update_fields=["follow_up_resuelto"])
    return HttpResponse("")
