"""Ficha de un registro: ver el detalle, ir a corregirlo o borrarlo con Deshacer.

Borrar guarda una copia del registro (con sus plantas y nutrientes) en la sesión
y lo borra; Deshacer, durante un minuto, lo vuelve a crear con los mismos ids.
Las mediciones de planta con foto no se pueden deshacer: al borrarlas se va el archivo.
"""
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import Cultivo, Evento, MedicionAmbiente, MedicionEC, MedicionPlanta, Planta, Riego, Tarea
from ..permissions import exigir_edicion, objeto_del_cultivo

# tipo → (modelo, nombre, url de corrección)
TIPOS = {
    "ambiente": (MedicionAmbiente, "Medición de ambiente", "medicion_ambiente_editar"),
    "riego": (Riego, "Riego", "riego_editar"),
    "evento": (Evento, "Evento", "evento_editar"),
    "ec": (MedicionEC, "Medición de pH / EC", "medicion_ec_editar"),
    "tarea": (Tarea, "Tarea", "tarea_editar"),
    "planta": (MedicionPlanta, "Medición de planta", "medicion_planta_editar"),
}
DESHACER_SEGUNDOS = 60


def _registro(request, tipo, pk):
    if tipo not in TIPOS:
        raise Http404("Tipo de registro desconocido")
    return objeto_del_cultivo(request, TIPOS[tipo][0], pk=pk)


def _con_hijos(obj):
    """El registro y lo que cuelga de él, en el orden en que hay que recrearlo."""
    if isinstance(obj, Riego):
        return [obj, *obj.detalle_plantas.all(), *obj.nutrientes_aplicados.all()]
    return [obj]


def _volver(request, defecto):
    destino = request.POST.get("volver") or request.GET.get("volver") or ""
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return defecto


@login_required
def registro_ficha(request, tipo, pk):
    obj = _registro(request, tipo, pk)
    cultivo = request.cultivo_actual
    if tipo == "evento" and obj.tipo == "nota":
        nombre = "Nota"
    else:
        nombre = TIPOS[tipo][1]
    return render(request, "growlog/registro_ficha.html", {
        "obj": obj, "tipo": tipo, "nombre": nombre, "cultivo": cultivo,
        "editar_url": reverse(f"growlog:{TIPOS[tipo][2]}", args=[obj.pk]),
        "se_puede_deshacer": not (tipo == "planta" and obj.foto),
        "volver": _volver(request, reverse("growlog:timeline", args=[cultivo.slug])),
    })


@require_POST
@login_required
def registro_borrar(request, tipo, pk):
    obj = _registro(request, tipo, pk)
    cultivo = request.cultivo_actual
    nombre = TIPOS[tipo][1]
    if not (tipo == "planta" and obj.foto):
        request.session["ultimo_borrado"] = {
            "t": time.time(), "nombre": nombre,
            "datos": serializers.serialize("json", _con_hijos(obj)),
        }
    else:
        request.session.pop("ultimo_borrado", None)
    obj.delete()
    messages.success(request, f"{nombre} borrado.", extra_tags="borrado")
    return redirect(_volver(request, reverse("growlog:timeline", args=[cultivo.slug])))


@require_POST
@login_required
def registro_restaurar(request):
    """Deshacer el último borrado de esta sesión, si fue hace menos de un minuto."""
    borrado = request.session.pop("ultimo_borrado", None) or {}
    if not borrado or time.time() - borrado.get("t", 0) > DESHACER_SEGUNDOS:
        messages.error(request, "Ya no se puede deshacer ese borrado.")
        return redirect(_volver(request, reverse("growlog:dashboard")))
    objetos = list(serializers.deserialize("json", borrado["datos"]))
    principal = objetos[0].object
    # Solo se restaura en un cultivo que sigue existiendo y donde todavía se puede editar.
    try:
        cultivo = principal.planta.cultivo if isinstance(principal, MedicionPlanta) else principal.cultivo
    except (Cultivo.DoesNotExist, Planta.DoesNotExist):
        raise Http404("El cultivo ya no existe")
    exigir_edicion(request.user, cultivo)
    try:
        with transaction.atomic():
            for o in objetos:
                o.save()
    except IntegrityError:
        # Algo de lo que usaba (una planta, un nutriente) ya no está.
        messages.error(request, "No se pudo deshacer: cambió algo de lo que usaba ese registro.")
        return redirect(_volver(request, reverse("growlog:timeline", args=[cultivo.slug])))
    messages.success(request, "Listo, volvió.")
    return redirect(_volver(request, reverse("growlog:timeline", args=[cultivo.slug])))
