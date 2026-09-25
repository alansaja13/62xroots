"""Persistencia atómica de una sesión de riego y su desglose por planta."""

from django.core.exceptions import ValidationError
from django.db import transaction

from growlog.models import NutrienteAplicado, Riego, RiegoPlanta
from .validacion import validar_solucion


@transaction.atomic
def guardar_riego(*, riego, detalles, nutrientes=None):
    """Reemplaza el desglose completo; nutrientes=None conserva los existentes.

    Recibe datos ya parseados por la interfaz. Valida invariantes antes de
    escribir y bloquea la cabecera existente para serializar sus modificaciones.
    La autorización corresponde al adaptador que obtuvo el cultivo/riego.
    """
    if not detalles:
        raise ValidationError("Seleccioná al menos una planta e indicá su volumen de riego.")
    validar_solucion(ph=riego.ph_agua, ec=riego.ec_solucion)

    if riego.pk:
        Riego.objects.select_for_update().get(pk=riego.pk)

    vistos = set()
    for detalle in detalles:
        planta = detalle["planta"]
        if planta.pk in vistos:
            raise ValidationError("Una planta no puede aparecer dos veces en el mismo riego.")
        vistos.add(planta.pk)
        if planta.cultivo_id != riego.cultivo_id:
            raise ValidationError("Todas las plantas deben pertenecer al cultivo del riego.")
        if detalle["volumen_ml"] <= 0:
            raise ValidationError("El volumen por planta debe ser mayor que cero.")
        validar_solucion(ph=detalle.get("ph_runoff"), ec=detalle.get("ec_runoff"))
        fila = RiegoPlanta(riego=riego, **detalle)
        fila.full_clean(exclude=["riego"], validate_unique=False)

    aplicaciones = []
    if nutrientes is not None:
        for nutriente, dosis in nutrientes:
            if not dosis.is_finite() or dosis <= 0:
                raise ValidationError("La dosis de nutrientes debe ser un número positivo.")
            aplicacion = NutrienteAplicado(riego=riego, nutriente=nutriente, dosis_g_por_litro=dosis)
            aplicacion.full_clean(exclude=["riego"])
            aplicaciones.append(aplicacion)

    riego.volumen_total_ml = sum(d["volumen_ml"] for d in detalles)
    riego.full_clean()
    riego.save()
    riego.detalle_plantas.exclude(planta_id__in=vistos).delete()
    for detalle in detalles:
        valores = {k: v for k, v in detalle.items() if k != "planta"}
        RiegoPlanta.objects.update_or_create(
            riego=riego, planta=detalle["planta"], defaults=valores,
        )
    if nutrientes is not None:
        riego.nutrientes_aplicados.all().delete()
        for aplicacion in aplicaciones:
            aplicacion.riego = riego
        NutrienteAplicado.objects.bulk_create(aplicaciones)
    return riego
