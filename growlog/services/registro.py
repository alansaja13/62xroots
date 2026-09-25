import hashlib
import json
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from growlog.models import Cultivo, Evento, MedicionAmbiente, MedicionEC, Nutriente, RegistroRecibido, Riego, Tarea
from growlog.permissions import cultivos_visibles, puede_editar
from growlog.registration_forms import AmbienteForm, ObservacionForm, ECForm, PendienteForm, SolucionForm, VolumenForm, NutrienteForm
from .riegos import guardar_riego


class RegistroError(Exception):
    def __init__(self, mensaje, status=400, campos=None):
        self.mensaje, self.status, self.campos = mensaje, status, campos or {}


def validar(form_class, datos):
    if not isinstance(datos, dict):
        raise RegistroError("Los datos deben ser un objeto.")
    desconocidos = set(datos) - set(form_class.base_fields)
    if desconocidos or any(isinstance(value, (dict, list, bool)) for value in datos.values()):
        raise RegistroError("El registro contiene campos desconocidos o valores inválidos.")
    form = form_class(datos)
    if not form.is_valid():
        raise RegistroError("Revisá los campos señalados.", campos=form.errors.get_json_data())
    return form.cleaned_data


@transaction.atomic
def recibir_registro(usuario, payload):
    if not isinstance(payload, dict) or set(payload) != {"id", "cultivo_id", "tipo", "observado_en", "datos"}:
        raise RegistroError("El formato del registro no es válido.")
    if not usuario.is_authenticated or not usuario.is_active:
        raise RegistroError("Iniciá sesión para sincronizar.", 401)
    try:
        operation = UUID(payload["id"])
        if type(payload["cultivo_id"]) is not int:
            raise ValueError
        observado = parse_datetime(payload["observado_en"])
        if observado is None or timezone.is_naive(observado):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise RegistroError("La identificación o fecha del registro no es válida. La fecha debe incluir zona horaria.")
    if observado > timezone.now() + timedelta(minutes=5):
        raise RegistroError("La fecha está en el futuro. Revisá la hora del dispositivo.")

    # Serializar las altas de un cultivo evita que dos reintentos creen registros
    # simultáneos en PostgreSQL. La restricción única también cubre UUID repetidos
    # entre distintos cultivos; get_or_create resuelve esa carrera en un savepoint.
    cultivo = Cultivo.objects.select_for_update().filter(pk=payload["cultivo_id"]).first()
    if cultivo is None or not cultivos_visibles(usuario).filter(pk=cultivo.pk).exists():
        raise RegistroError("Este cultivo ya no está disponible para tu cuenta.", 404)
    if not puede_editar(usuario, cultivo):
        raise RegistroError("Ya no tenés permiso para registrar en este cultivo.", 403)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    recibo, nuevo = RegistroRecibido.objects.get_or_create(
        usuario=usuario, operacion_id=operation,
        defaults={"cultivo": cultivo, "contenido_hash": fingerprint},
    )
    if not nuevo:
        if recibo.contenido_hash != fingerprint:
            raise RegistroError("Ese identificador ya confirmó otro contenido. Revisá el registro antes de reenviarlo.", 409)
        return recibo.resultado, False

    tipo, datos = payload["tipo"], payload["datos"]
    common = {"cultivo": cultivo, "creado_por": usuario}
    if tipo == "ambiente":
        obj = MedicionAmbiente(timestamp=observado, **common, **validar(AmbienteForm, datos))
    elif tipo == "evento":
        obj = Evento(timestamp=observado, **common, **validar(ObservacionForm, datos))
    elif tipo == "ec":
        obj = MedicionEC(timestamp=observado, **common, **validar(ECForm, datos))
    elif tipo == "tarea":
        obj = Tarea(**common, **validar(PendienteForm, datos))
    elif tipo == "riego":
        if not isinstance(datos, dict):
            raise RegistroError("Los datos del riego deben ser un objeto.")
        datos = dict(datos)
        plantas = datos.pop("plantas", [])
        nutrientes = datos.pop("nutrientes", [])
        if not isinstance(plantas, list) or not isinstance(nutrientes, list) or len(plantas) > 200 or len(nutrientes) > 100:
            raise RegistroError("El desglose del riego no es válido.")
        solucion = validar(SolucionForm, datos)
        disponibles = {p.pk: p for p in cultivo.plantas.activas()}
        detalles = []
        for row in plantas:
            values = validar(VolumenForm, row)
            planta = disponibles.get(values.pop("planta_id"))
            if planta is None:
                raise RegistroError("Una planta ya no está disponible en este cultivo. Revisá el riego.", 409)
            detalles.append({"planta": planta, **values})
        aplicaciones, vistos = [], set()
        for row in nutrientes:
            values = validar(NutrienteForm, row)
            nutriente = Nutriente.objects.filter(pk=values["nutriente_id"]).first()
            if nutriente is None or nutriente.pk in vistos:
                raise RegistroError("Revisá los nutrientes: deben existir y no repetirse.")
            vistos.add(nutriente.pk)
            aplicaciones.append((nutriente, values["dosis_g_por_litro"]))
        obj = Riego(timestamp=observado, ph_agua=solucion["ph"], ec_solucion=solucion["ec"], notas=solucion["notas"], **common)
        try:
            guardar_riego(riego=obj, detalles=detalles, nutrientes=aplicaciones)
        except ValidationError as exc:
            raise RegistroError(" ".join(exc.messages))
    else:
        raise RegistroError("Tipo de registro desconocido.")
    if tipo != "riego":
        try:
            obj.full_clean()
            obj.save()
        except ValidationError as exc:
            raise RegistroError(" ".join(exc.messages))
    recibo.resultado = {"id": str(operation), "tipo": tipo, "registro_id": obj.pk, "observado_en": observado.isoformat(), "recibido_en": recibo.recibido_en.isoformat()}
    recibo.save(update_fields=["resultado"])
    return recibo.resultado, True
