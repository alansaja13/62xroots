"""Política de acceso por cultivo; staff no concede acceso global a la bitácora."""

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import Cultivo, Equipo, TarifaElectrica

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def cultivos_visibles(usuario, *, editar=False):
    if not usuario.is_authenticated or not usuario.is_active:
        return Cultivo.objects.none()
    miembros = Q(miembros__usuario=usuario)
    if editar:
        miembros &= Q(miembros__rol="editor")
    return Cultivo.objects.filter(Q(propietario=usuario) | miembros).distinct()


def puede_editar(usuario, cultivo):
    if not usuario.is_authenticated or not usuario.is_active:
        return False
    return cultivo.propietario_id == usuario.pk or cultivo.miembros.filter(usuario=usuario, rol="editor").exists()


def exigir_edicion(usuario, cultivo):
    if not puede_editar(usuario, cultivo):
        raise PermissionDenied("Tenés acceso de solo lectura a este cultivo.")


# Relaciones explícitas para resolver el cultivo de cada recurso sin depender
# del autor del registro, que puede ser un colaborador.
RELACION_CULTIVO = {
    "Cultivo": "", "Planta": "cultivo", "Tarea": "cultivo", "Evento": "cultivo",
    "Riego": "cultivo", "MedicionEC": "cultivo", "CambioFotoperiodo": "cultivo",
    "CanopySnapshot": "cultivo", "MedicionAmbiente": "cultivo",
    "NutrienteAplicado": "riego__cultivo", "RiegoPlanta": "riego__cultivo",
    "MedicionPlanta": "planta__cultivo", "CambioEtapaPlanta": "planta__cultivo",
}


def objeto_del_cultivo(request, model, *, editar=False, **lookup):
    relacion = RELACION_CULTIVO[model.__name__]
    filtro = f"{relacion}__in" if relacion else "pk__in"
    qs = model.objects.filter(**{filtro: cultivos_visibles(request.user)})
    if relacion:
        qs = qs.select_related(relacion)
    obj = get_object_or_404(qs, **lookup)
    cultivo = obj
    for atributo in relacion.split("__") if relacion else []:
        cultivo = getattr(cultivo, atributo)
    if editar or request.method not in SAFE_METHODS:
        exigir_edicion(request.user, cultivo)
    request.cultivo_actual = cultivo
    request.puede_editar_cultivo = puede_editar(request.user, cultivo)
    return obj


def recursos_visibles(model, usuario, *, editar=False):
    if not usuario.is_authenticated or not usuario.is_active:
        return model.objects.none()
    propios = Q(propietario=usuario)
    if editar:
        return model.objects.filter(propios)
    return model.objects.filter(propios | Q(costos__cultivo__in=cultivos_visibles(usuario))).distinct()


def tarifas_del_cultivo(cultivo):
    return TarifaElectrica.objects.filter(costos__cultivo=cultivo).distinct()


def equipos_asignables(usuario, cultivo):
    # Solo recursos propios o ya vinculados a este cultivo. Compartir un
    # cultivo no comparte todo el inventario privado de su propietario.
    return Equipo.objects.filter(Q(propietario=usuario) | Q(costos__cultivo=cultivo)).distinct()
