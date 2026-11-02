"""Más: todo lo que no entra en la barra (secciones del cultivo, cosas generales, preferencias y salir)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..context_processors import cultivo_destino, cultivos_del_menu, pestanas_cultivo
from ..permissions import puede_editar


@login_required
def mas(request):
    grupos = cultivos_del_menu(request.user)
    cultivo = cultivo_destino(request, None, grupos)
    secciones = []
    if cultivo is not None:
        editable = puede_editar(request.user, cultivo)
        # Resumen ya está en la barra como "Cultivo".
        secciones = [p for p in pestanas_cultivo(cultivo, puede_editar=editable, seccion=None)
                     if p["seccion"] != "resumen"]
    return render(request, "growlog/mas.html", {
        "cultivo": cultivo,
        "secciones": secciones,
        "es_duenio_de_alguno": any(c.propietario_id == request.user.pk for c in grupos["activos"] + grupos["historial"]),
    })
