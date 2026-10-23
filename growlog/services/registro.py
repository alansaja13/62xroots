"""Alta de registros diarios desde Registrar: ambiente, riego, observación, EC/pH y tarea."""
from django.core.exceptions import ValidationError
from django.db import transaction

from growlog.models import Evento, MedicionAmbiente, MedicionEC, Riego, Tarea
from growlog.permissions import nutrientes_para
from growlog.registration_forms import (
    AmbienteForm, ObservacionForm, ECForm, NutrienteForm, PendienteForm, RiegoSolucionForm, VolumenForm,
)
from .riegos import guardar_riego

TIPOS = ("ambiente", "riego", "evento", "ec", "tarea")


class RegistroError(Exception):
    def __init__(self, mensaje, campos=None):
        super().__init__(mensaje)
        self.mensaje, self.campos = mensaje, campos or {}


def validar(form_class, datos):
    form = form_class(datos)
    if not form.is_valid():
        raise RegistroError("Revisá los campos señalados.", campos=form.errors)
    return form.cleaned_data


@transaction.atomic
def guardar_registro(usuario, cultivo, tipo, observado, datos):
    """Crea el registro. La vista ya comprobó que `usuario` puede editar `cultivo`.

    `datos` trae los campos del formulario del tipo; riego suma `plantas`
    ([{planta_id, volumen_ml, ...}]) y `nutrientes`, y evento `plantas_afectadas` (ids).
    """
    common = {"cultivo": cultivo, "creado_por": usuario}
    datos = dict(datos)
    if tipo == "ambiente":
        obj = MedicionAmbiente(timestamp=observado, **common, **validar(AmbienteForm, datos))
    elif tipo == "evento":
        plantas_ids = datos.pop("plantas_afectadas", [])
        plantas_afectadas = list(cultivo.plantas.activas().filter(pk__in=plantas_ids))
        if len(plantas_afectadas) != len(set(plantas_ids)):
            raise RegistroError("Una planta ya no está disponible en este cultivo. Revisá el evento.")
        obj = Evento(timestamp=observado, **common, **validar(ObservacionForm, datos))
    elif tipo == "ec":
        obj = MedicionEC(timestamp=observado, **common, **validar(ECForm, datos))
    elif tipo == "tarea":
        obj = Tarea(**common, **validar(PendienteForm, datos))
    elif tipo == "riego":
        plantas = datos.pop("plantas", [])
        nutrientes = datos.pop("nutrientes", [])
        solucion = validar(RiegoSolucionForm, datos)
        disponibles = {p.pk: p for p in cultivo.plantas.activas()}
        detalles = []
        for row in plantas:
            values = validar(VolumenForm, row)
            planta = disponibles.get(values.pop("planta_id"))
            if planta is None:
                raise RegistroError("Una planta ya no está disponible en este cultivo. Revisá el riego.")
            detalles.append({"planta": planta, **values})
        aplicaciones = []
        for row in nutrientes:
            values = validar(NutrienteForm, row)
            nutriente = nutrientes_para(usuario, cultivo).filter(pk=values["nutriente_id"]).first()
            if nutriente is None:
                raise RegistroError("Revisá los nutrientes: alguno ya no existe.")
            aplicaciones.append((nutriente, values["dosis_g_por_litro"]))
        obj = Riego(
            timestamp=observado, ph_agua=solucion["ph"], ec_solucion=solucion["ec"], notas=solucion["notas"],
            buscar_runoff=solucion["buscar_runoff"], **common,
        )
        try:
            guardar_riego(riego=obj, detalles=detalles, nutrientes=aplicaciones)
        except ValidationError as exc:
            raise RegistroError(" ".join(exc.messages))
        return obj
    else:
        raise RegistroError("Tipo de registro desconocido.")
    try:
        obj.full_clean()
        obj.save()
    except ValidationError as exc:
        raise RegistroError(" ".join(exc.messages))
    if tipo == "evento":
        obj.plantas_afectadas.set(plantas_afectadas)
    return obj
