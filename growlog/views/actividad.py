"""Panel de actividad: quién entra y quién registra. Solo para superusuarios."""
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from ..services.actividad import resumen_actividad


@login_required
def actividad(request):
    if not request.user.is_superuser:
        raise Http404
    return render(request, "growlog/actividad.html", resumen_actividad())
