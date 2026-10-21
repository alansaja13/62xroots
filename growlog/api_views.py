import hashlib
import json
from datetime import date, time
from decimal import Decimal, InvalidOperation
from functools import partial, wraps

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import (
    APIToken, CambioFotoperiodo, CanopySnapshot, ColaPosicion,
    CostoEnergetico, Cultivo, Equipo, Evento, LecturaMedidor,
    MedicionAmbiente, MedicionEC, MedicionPlanta, Nutriente, NutrienteAplicado,
    ParametroIdeal, Planta, POSICION_TENT_COORDS, Riego, Tarea, TarifaElectrica,
)
from .services.energia import calcular_meses, ciclo_activo
from .services.riegos import guardar_riego
from .permissions import (SAFE_METHODS, cultivos_visibles, puede_editar, recursos_visibles, tarifas_del_cultivo, equipos_asignables)

EVENTO_TIPOS = {c[0] for c in Evento.TIPO_CHOICES}
TAREA_PRIORIDADES = {c[0] for c in Tarea.PRIORIDAD_CHOICES}
TAREA_CATEGORIAS = {c[0] for c in Tarea.CATEGORIA_CHOICES}
PLANTA_POSICIONES = {c[0] for c in Planta.POSICION_CHOICES}
PLANTA_ESTADOS = {c[0] for c in Planta.ESTADO_CHOICES}
MEDICION_EC_TIPOS = {c[0] for c in MedicionEC.TIPO_CHOICES}
ASPECTO_CHOICES = {c[0] for c in MedicionPlanta.ASPECTO_CHOICES}
EQUIPO_CATEGORIAS = {c[0] for c in Equipo.CATEGORIA_CHOICES}
SMALLINT_MAX = 32767

# ── Helpers ──────────────────────────────────────────────────────────────────

def api_ok(data, status=200):
    return JsonResponse({'ok': True, 'data': data}, status=status)


def api_error(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


class ApiInputError(ValueError):
    """Error de la petición: require_token lo convierte en una respuesta JSON."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


_VERDADEROS = {'true', '1', 'si', 'sí', 'yes', 'on'}
_FALSOS = {'false', '0', 'no', 'off', ''}


def _flag(value, campo):
    """bool('false') es True: interpretar el valor en vez de su 'truthiness'."""
    if isinstance(value, bool) or value is None:
        return bool(value)
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in _VERDADEROS | _FALSOS:
        return value.strip().lower() in _VERDADEROS
    raise ApiInputError(f'{campo} debe ser true o false')


def require_token(view_func):
    """Autentica por Bearer token y resuelve el cultivo (o planta) de la URL.

    Deja request.api_user, request.api_cultivo y, en rutas de planta,
    request.api_planta. Los ApiInputError de la vista se responden como JSON.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Bearer '):
            return api_error('Authentication required', 401)
        token_str = auth[7:].strip()
        if not token_str:
            return api_error('Authentication required', 401)
        token_hash = hashlib.sha256(token_str.encode()).hexdigest()
        try:
            token = APIToken.objects.select_related('user').get(token_hash=token_hash)
        except APIToken.DoesNotExist:
            return api_error('Invalid token', 401)
        if not token.user.is_active:
            return api_error('Invalid token', 401)
        request.api_user = token.user
        request.api_token_hash = token_hash
        cultivo = None
        if 'slug' in kwargs:
            cultivo = cultivos_visibles(token.user).filter(slug=kwargs['slug']).first()
            if cultivo is None:
                return api_error('Cultivo no encontrado', 404)
        elif 'planta_uuid' in kwargs:
            planta = Planta.objects.select_related('cultivo').filter(
                uuid=kwargs['planta_uuid'], cultivo__in=cultivos_visibles(token.user)
            ).first()
            if planta is None:
                return api_error('Planta no encontrada', 404)
            request.api_planta = planta
            cultivo = planta.cultivo
        request.api_cultivo = cultivo
        if cultivo and request.method not in SAFE_METHODS and not puede_editar(token.user, cultivo):
            return api_error('Tenés acceso de solo lectura a este cultivo', 403)
        try:
            return view_func(request, *args, **kwargs)
        except ApiInputError as exc:
            return api_error(str(exc), exc.status)
    return wrapper


def _limitar_escrituras(request):
    """60 writes por hora por token."""
    key = f"api_writes_{request.api_token_hash}"
    count = cache.get(key, 0)
    if count >= 60:
        raise ApiInputError('Rate limit exceeded: 60 writes/hour', 429)
    cache.set(key, count + 1, timeout=3600)


def _body(request):
    """Cuenta la escritura y devuelve el body JSON, que debe ser un objeto."""
    _limitar_escrituras(request)
    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiInputError('Invalid JSON body')
    if not isinstance(data, dict):
        raise ApiInputError('El cuerpo JSON debe ser un objeto')
    return data


def _buscar(qs, pk, mensaje):
    try:
        return qs.get(pk=pk)
    except qs.model.DoesNotExist:
        raise ApiInputError(mensaje, 404)


def _mensajes(exc):
    if hasattr(exc, 'error_dict'):
        return '; '.join(
            msg if campo == '__all__' else f'{campo}: {msg}'
            for campo, msgs in exc.message_dict.items() for msg in msgs
        )
    return '; '.join(exc.messages)


def _guardar(obj):
    """Valida con las reglas del modelo (las mismas que web y Registrar) y guarda."""
    try:
        obj.full_clean()
    except ValidationError as exc:
        raise ApiInputError(_mensajes(exc))
    obj.save()
    return obj


def _borrar(request, obj, *, en_uso=None):
    _limitar_escrituras(request)
    obj_id = obj.id
    try:
        obj.delete()
    except IntegrityError:
        if en_uso is None:
            raise
        raise ApiInputError(en_uso, 409)
    return api_ok({'deleted': obj_id})


def _no_permitido():
    return api_error('Method not allowed', 405)


# ── Lectura de campos del body ───────────────────────────────────────────────
# Cada lector recibe (body, campo) y devuelve el valor limpio o lanza
# ApiInputError. Los diccionarios CAMPOS_* sirven igual para POST y PATCH.

def _valor(body, campo, requerido, default=None):
    valor = body.get(campo, default)
    if valor is None and requerido:
        raise ApiInputError(f'{campo} es requerido')
    return valor


def _rango(campo, minimo, maximo):
    if minimo is not None and maximo is not None:
        return f'{campo} fuera de rango ({minimo}-{maximo})'
    if minimo is not None:
        return f'{campo} debe ser mayor o igual que {minimo}'
    return f'{campo} debe ser menor o igual que {maximo}'


def _decimal(body, campo, *, requerido=False, minimo=None, maximo=None, positivo=False):
    valor = _valor(body, campo, requerido)
    if valor is None:
        return None
    try:
        if isinstance(valor, bool):
            raise InvalidOperation
        numero = Decimal(str(valor))
    except InvalidOperation:
        raise ApiInputError(f'{campo} debe ser un número')
    if not numero.is_finite():
        raise ApiInputError(f'{campo} debe ser un número')
    if positivo and numero <= 0:
        raise ApiInputError(f'{campo} debe ser positivo')
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        raise ApiInputError(_rango(campo, minimo, maximo))
    return numero


def _entero(body, campo, *, requerido=False, minimo=None, maximo=None):
    valor = _valor(body, campo, requerido)
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        raise ApiInputError(f'{campo} debe ser un número entero')
    try:
        numero = int(valor)
    except ValueError:
        raise ApiInputError(f'{campo} debe ser un número entero')
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        raise ApiInputError(_rango(campo, minimo, maximo))
    return numero


def _iso(body, campo, requerido, parser, formato):
    valor = body.get(campo)
    if valor in (None, ''):
        if requerido:
            raise ApiInputError(f'{campo} es requerido ({formato})')
        return None
    if not isinstance(valor, str):
        raise ApiInputError(f'{campo} debe ser {formato}')
    try:
        return parser(valor.strip())
    except ValueError:
        raise ApiInputError(f'{campo} debe ser {formato}')


def _fecha(body, campo, *, requerido=False):
    return _iso(body, campo, requerido, date.fromisoformat, 'YYYY-MM-DD')


def _hora(body, campo, *, requerido=False):
    return _iso(body, campo, requerido, time.fromisoformat, 'HH:MM o HH:MM:SS')


def _texto(body, campo, *, largo, requerido=False, default=''):
    valor = body.get(campo, default)
    valor = '' if valor is None else str(valor)
    if not requerido:
        return valor[:largo]
    valor = valor.strip()
    if not valor:
        raise ApiInputError(f'{campo} es requerido')
    if len(valor) > largo:
        raise ApiInputError(f'{campo} demasiado largo (máx {largo} caracteres)')
    return valor


def _opcion(body, campo, *, opciones, default=None):
    valor = body.get(campo, default)
    if not isinstance(valor, str) or valor not in opciones:
        raise ApiInputError(f'{campo} inválido. Opciones: {sorted(opciones)}')
    return valor


def _bool(body, campo, *, default=False):
    return _flag(body.get(campo, default), campo)


def _leer(body, campos, *, parcial=False):
    """Lee los campos del body. parcial=True (PATCH) solo lee los presentes."""
    return {
        campo: lector(body, campo)
        for campo, lector in campos.items()
        if not parcial or campo in body
    }


def _aplicar(obj, body, campos):
    for campo, valor in _leer(body, campos, parcial=True).items():
        setattr(obj, campo, valor)


_notas = partial(_texto, largo=500)
_ph = partial(_decimal, minimo=0, maximo=14)
_ec = partial(_decimal, minimo=0)


def _plantas_por_uuid(qs, uuids, campo):
    if not isinstance(uuids, list):
        raise ApiInputError(f'{campo} debe ser una lista de uuids')
    por_uuid = {str(p.uuid): p for p in qs}
    plantas = []
    for uuid_str in uuids:
        planta = por_uuid.get(str(uuid_str))
        if planta is None:
            raise ApiInputError(f'planta_uuid desconocido o archivado: {uuid_str}')
        plantas.append(planta)
    return plantas


# ── Serializers ───────────────────────────────────────────────────────────────

def _num(valor):
    return str(valor) if valor is not None else None


def _cultivo_base(c):
    return {
        'id': c.id,
        'slug': c.slug,
        'nombre': c.nombre,
        'estado': c.estado,
        'fecha_inicio': c.fecha_inicio.isoformat(),
        'dias_desde_inicio': c.dias_desde_inicio,
        'lampara_watts_reales': c.lampara_watts_reales,
        'sustrato': c.sustrato,
        'carpa_dimensiones': c.carpa_dimensiones,
    }


def _planta(p):
    return {'id': p.id, 'uuid': str(p.uuid), 'apodo': p.apodo, 'strain': p.strain, 'estado': p.estado}


def _planta_full(p):
    return {
        'id': p.id, 'uuid': str(p.uuid), 'apodo': p.apodo, 'strain': p.strain,
        'estado': p.estado, 'estado_display': p.get_estado_display(),
        'posicion_tent': p.posicion_tent, 'posicion_tent_display': p.get_posicion_tent_display(),
        'dias_flora_estimados': p.dias_flora_estimados,
        'indica_sativa_ratio': p.indica_sativa_ratio,
        'thc_estimado': _num(p.thc_estimado),
        'yield_estimado_g': p.yield_estimado_g,
        'yield_real_g': p.yield_real_g,
        'notas_genetica': p.notas_genetica,
        'archivado': p.archivado,
    }


def _riego_planta(rp):
    return {
        'id': rp.id,
        'planta': {'uuid': str(rp.planta.uuid), 'apodo': rp.planta.apodo},
        'volumen_ml': rp.volumen_ml,
        'runoff_observado': rp.runoff_observado,
        'ph_runoff': _num(rp.ph_runoff),
        'ec_runoff': _num(rp.ec_runoff),
        'notas': rp.notas,
    }


def _nutriente_aplicado(na):
    return {
        'id': na.id, 'nutriente_id': na.nutriente_id, 'nutriente': str(na.nutriente),
        'dosis_g_por_litro': str(na.dosis_g_por_litro),
    }


def _riego(r, include_nutrientes=True, include_plantas=True):
    d = {
        'id': r.id,
        'timestamp': r.timestamp.isoformat(),
        'volumen_total_ml': r.volumen_total_ml,
        'volumen_por_planta_ml': r.volumen_por_planta_ml,
        'ph_agua': _num(r.ph_agua),
        'ec_solucion': _num(r.ec_solucion),
        'buscar_runoff': r.buscar_runoff,
        'runoff_observado': r.runoff_observado,
        'notas': r.notas,
    }
    if include_nutrientes:
        d['nutrientes_aplicados'] = [
            _nutriente_aplicado(na) for na in r.nutrientes_aplicados.select_related('nutriente').all()
        ]
    if include_plantas:
        d['detalle_plantas'] = [
            _riego_planta(rp) for rp in r.detalle_plantas.select_related('planta').all()
        ]
    return d


def _cambio_fotoperiodo(cf):
    return {
        'id': cf.id,
        'fotoperiodo': cf.fotoperiodo,
        'hora_lights_on': cf.hora_lights_on.isoformat(),
        'fecha_inicio': cf.fecha_inicio.isoformat(),
        'notas': cf.notas,
    }


def _medicion(m):
    return {
        'id': m.id,
        'timestamp': m.timestamp.isoformat(),
        'temperatura_c': str(m.temperatura_c),
        'humedad_relativa': str(m.humedad_relativa),
        'vpd': m.vpd,
        'vpd_estado': m.vpd_estado,
        'luz_estado': m.luz_estado,
        'luz_estado_display': m.get_luz_estado_display() if m.luz_estado else None,
        'notas': m.notas,
    }


def _evento(e):
    return {
        'id': e.id,
        'timestamp': e.timestamp.isoformat(),
        'tipo': e.tipo,
        'tipo_display': e.get_tipo_display(),
        'descripcion': e.descripcion,
        'plantas_afectadas': [p.apodo for p in e.plantas_afectadas.all()],
        'follow_up_fecha': e.follow_up_fecha.isoformat() if e.follow_up_fecha else None,
        'follow_up_resuelto': e.follow_up_resuelto,
    }


def _tarea(t):
    return {
        'id': t.id,
        'titulo': t.titulo,
        'descripcion': t.descripcion,
        'prioridad': t.prioridad,
        'categoria': t.categoria,
        'fecha_objetivo': t.fecha_objetivo.isoformat() if t.fecha_objetivo else None,
        'completada': t.completada,
        'completada_en': t.completada_en.isoformat() if t.completada_en else None,
    }


def _medicion_planta(m):
    return {
        'id': m.id,
        'fecha': m.fecha.isoformat(),
        'altura_cm': _num(m.altura_cm),
        'nudos_count': m.nudos_count,
        'ancho_canopy_cm': _num(m.ancho_canopy_cm),
        'aspecto_general': m.aspecto_general,
        'sintomas': m.sintomas,
    }


def _medicion_ec_ser(m):
    return {
        'id': m.id,
        'timestamp': m.timestamp.isoformat(),
        'tipo': m.tipo,
        'tipo_display': m.get_tipo_display(),
        'ph': _num(m.ph),
        'ec': _num(m.ec),
        'temp_agua': _num(m.temp_agua),
        'notas': m.notas,
    }


# ── Read endpoints ────────────────────────────────────────────────────────────

@require_GET
@require_token
def cultivos_list(request):
    cultivos = cultivos_visibles(request.api_user).filter(archivado=False)
    return api_ok([_cultivo_base(c) for c in cultivos])


@require_GET
@require_token
def cultivo_detail(request, slug):
    c = request.api_cultivo
    data = _cultivo_base(c)
    data['notas'] = c.notas
    data['plantas'] = [_planta(p) for p in c.plantas.filter(archivado=False)]
    data['ultimos_riegos'] = [_riego(r, include_nutrientes=False, include_plantas=False) for r in c.riegos.all()[:5]]
    data['ultimas_mediciones'] = [_medicion(m) for m in c.mediciones.all()[:5]]
    data['ultimos_eventos'] = [
        _evento(e) for e in c.eventos.prefetch_related('plantas_afectadas').all()[:10]
    ]
    data['tareas_pendientes'] = [_tarea(t) for t in c.tareas.filter(completada=False)]
    data['cambios_fotoperiodo'] = [_cambio_fotoperiodo(cf) for cf in c.cambios_fotoperiodo.all()]
    return api_ok(data)


# ── Riegos ────────────────────────────────────────────────────────────────────

CAMPOS_RIEGO = {
    'ph_agua': _ph,
    'ec_solucion': _ec,
    'buscar_runoff': _bool,
    'notas': _notas,
}

CAMPOS_DETALLE_PLANTA = {
    'volumen_ml': partial(_entero, requerido=True, minimo=1),
    'runoff_observado': _bool,
    'ph_runoff': _ph,
    'ec_runoff': _ec,
    'notas': _notas,
}


def _nutriente_y_dosis(item):
    if not isinstance(item, dict):
        raise ApiInputError('Cada nutriente debe ser un objeto')
    nutriente_id = _entero(item, 'nutriente_id', requerido=True)
    dosis = _decimal(item, 'dosis_g_por_litro', requerido=True, positivo=True)
    nutriente = Nutriente.objects.filter(pk=nutriente_id).first()
    if nutriente is None:
        raise ApiInputError(f'nutriente_id {nutriente_id} no existe')
    return nutriente, dosis


def _detalles_actuales(riego):
    return [
        {'planta': rp.planta, **{campo: getattr(rp, campo) for campo in CAMPOS_DETALLE_PLANTA}}
        for rp in riego.detalle_plantas.select_related('planta')
    ]


def _guardar_riego(riego, detalles, nutrientes=None):
    """El desglose por planta siempre pasa por guardar_riego (valida y recalcula el total)."""
    try:
        guardar_riego(riego=riego, detalles=detalles, nutrientes=nutrientes)
    except ValidationError as exc:
        raise ApiInputError('; '.join(exc.messages))


@csrf_exempt
@require_token
def cultivo_riegos(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        riegos = c.riegos.prefetch_related('nutrientes_aplicados__nutriente', 'detalle_plantas__planta').all()
        return api_ok([_riego(r) for r in riegos])

    if request.method == 'POST':
        body = _body(request)
        # detalle_plantas: [{planta_uuid, volumen_ml, runoff_observado?, ph_runoff?, ec_runoff?, notas?}, ...]
        # volumen_total_ml se calcula como la suma de estas filas — es requerido al menos una.
        detalle_raw = body.get('detalle_plantas', [])
        if not isinstance(detalle_raw, list) or not detalle_raw:
            raise ApiInputError('detalle_plantas es requerido: lista de {planta_uuid, volumen_ml}')
        if not all(isinstance(item, dict) for item in detalle_raw):
            raise ApiInputError('Cada detalle de planta debe ser un objeto')
        plantas = _plantas_por_uuid(
            c.plantas.activas(), [item.get('planta_uuid', '') for item in detalle_raw], 'detalle_plantas',
        )
        detalles = [
            {'planta': planta, **_leer(item, CAMPOS_DETALLE_PLANTA)}
            for planta, item in zip(plantas, detalle_raw)
        ]

        nutrientes_raw = body.get('nutrientes', [])
        if not isinstance(nutrientes_raw, list):
            raise ApiInputError('nutrientes debe ser una lista')
        nutrientes = [_nutriente_y_dosis(item) for item in nutrientes_raw]

        riego = Riego(cultivo=c, creado_por=request.api_user, **_leer(body, CAMPOS_RIEGO))
        _guardar_riego(riego, detalles, nutrientes)
        return api_ok(_riego(riego), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_riego_detail(request, slug, riego_id):
    riego = _buscar(
        request.api_cultivo.riegos.prefetch_related('nutrientes_aplicados__nutriente', 'detalle_plantas__planta'),
        riego_id, 'Riego no encontrado',
    )

    if request.method == 'GET':
        return api_ok(_riego(riego))

    if request.method == 'PATCH':
        _aplicar(riego, _body(request), CAMPOS_RIEGO)
        _guardar(riego)
        return api_ok(_riego(riego))

    if request.method == 'DELETE':
        return _borrar(request, riego)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_riego_plantas(request, slug, riego_id):
    """GET lista / POST agrega una fila de detalle por planta a un riego existente."""
    c = request.api_cultivo
    riego = _buscar(c.riegos, riego_id, 'Riego no encontrado')

    if request.method == 'GET':
        return api_ok([_riego_planta(rp) for rp in riego.detalle_plantas.select_related('planta').all()])

    if request.method == 'POST':
        body = _body(request)
        planta, = _plantas_por_uuid(c.plantas.activas(), [body.get('planta_uuid', '')], 'planta_uuid')
        if riego.detalle_plantas.filter(planta=planta).exists():
            raise ApiInputError('Esa planta ya tiene un detalle en este riego, usá PATCH para modificarlo')
        nuevo = {'planta': planta, **_leer(body, CAMPOS_DETALLE_PLANTA)}
        _guardar_riego(riego, _detalles_actuales(riego) + [nuevo])
        rp = riego.detalle_plantas.select_related('planta').get(planta=planta)
        return api_ok(_riego_planta(rp), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_riego_nutrientes(request, slug, riego_id):
    """GET lista / POST agrega un nutriente aplicado a un riego existente."""
    riego = _buscar(request.api_cultivo.riegos, riego_id, 'Riego no encontrado')

    if request.method == 'GET':
        return api_ok([
            _nutriente_aplicado(na) for na in riego.nutrientes_aplicados.select_related('nutriente').all()
        ])

    if request.method == 'POST':
        nutriente, dosis = _nutriente_y_dosis(_body(request))
        na = _guardar(NutrienteAplicado(riego=riego, nutriente=nutriente, dosis_g_por_litro=dosis))
        return api_ok(_nutriente_aplicado(na), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def riego_planta_detail(request, slug, riego_id, rp_id):
    """PATCH/DELETE de una fila de detalle por planta dentro de un riego.
    Actualizar volumen_ml re-sincroniza Riego.volumen_total_ml."""
    riego = _buscar(request.api_cultivo.riegos, riego_id, 'Riego no encontrado')
    rp = _buscar(riego.detalle_plantas.select_related('planta'), rp_id, 'Detalle de planta no encontrado')

    if request.method == 'GET':
        return api_ok(_riego_planta(rp))

    if request.method == 'PATCH':
        cambios = _leer(_body(request), CAMPOS_DETALLE_PLANTA, parcial=True)
        detalles = [
            {**d, **cambios} if d['planta'].pk == rp.planta_id else d
            for d in _detalles_actuales(riego)
        ]
        _guardar_riego(riego, detalles)
        rp.refresh_from_db()
        return api_ok(_riego_planta(rp))

    if request.method == 'DELETE':
        _limitar_escrituras(request)
        detalles = [d for d in _detalles_actuales(riego) if d['planta'].pk != rp.planta_id]
        if not detalles:
            raise ApiInputError('No se puede eliminar la última planta del riego. Eliminá el riego completo en su lugar.')
        _guardar_riego(riego, detalles)
        return api_ok({'deleted': rp.id})

    return _no_permitido()


@csrf_exempt
@require_token
def riego_nutriente_detail(request, slug, riego_id, na_id):
    riego = _buscar(request.api_cultivo.riegos, riego_id, 'Riego no encontrado')
    na = _buscar(riego.nutrientes_aplicados, na_id, 'Nutriente aplicado no encontrado')

    if request.method == 'DELETE':
        return _borrar(request, na)

    return _no_permitido()


# ── Mediciones ────────────────────────────────────────────────────────────────

CAMPOS_MEDICION = {
    'temperatura_c': partial(_decimal, requerido=True, minimo=0, maximo=60),
    'humedad_relativa': partial(_decimal, requerido=True, minimo=0, maximo=100),
    'notas': _notas,
}

CAMPOS_MEDICION_PLANTA = {
    'fecha': partial(_fecha, requerido=True),
    'altura_cm': partial(_decimal, minimo=0),
    'nudos_count': partial(_entero, minimo=0, maximo=SMALLINT_MAX),
    'ancho_canopy_cm': partial(_decimal, minimo=0),
    'aspecto_general': partial(_opcion, opciones=ASPECTO_CHOICES, default='bueno'),
    'sintomas': partial(_texto, largo=2000),
}

CAMPOS_MEDICION_EC = {
    'tipo': partial(_opcion, opciones=MEDICION_EC_TIPOS, default='solucion'),
    'ph': _ph,
    'ec': _ec,
    'temp_agua': partial(_decimal, minimo=0, maximo=60),
    'notas': _notas,
}


@csrf_exempt
@require_token
def cultivo_mediciones(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        return api_ok([_medicion(m) for m in c.mediciones.all()])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_MEDICION)
        m = _guardar(MedicionAmbiente(cultivo=c, creado_por=request.api_user, **datos))
        return api_ok(_medicion(m), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_medicion_detail(request, slug, medicion_id):
    m = _buscar(request.api_cultivo.mediciones, medicion_id, 'Medición no encontrada')

    if request.method == 'GET':
        return api_ok(_medicion(m))

    if request.method == 'PATCH':
        _aplicar(m, _body(request), CAMPOS_MEDICION)
        _guardar(m)
        return api_ok(_medicion(m))

    if request.method == 'DELETE':
        return _borrar(request, m)

    return _no_permitido()


@csrf_exempt
@require_token
def planta_mediciones(request, planta_uuid):
    """GET lista / POST crea una MedicionPlanta. La foto no se acepta por este
    endpoint JSON — usar la interfaz web para subir fotos."""
    p = request.api_planta

    if request.method == 'GET':
        return api_ok([_medicion_planta(m) for m in p.mediciones.all()])

    if request.method == 'POST':
        body = _body(request)
        if not body.get('fecha'):
            body['fecha'] = timezone.localdate().isoformat()
        datos = _leer(body, CAMPOS_MEDICION_PLANTA)
        m = _guardar(MedicionPlanta(planta=p, creado_por=request.api_user, **datos))
        return api_ok(_medicion_planta(m), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def medicion_planta_detail(request, planta_uuid, medicion_id):
    m = _buscar(request.api_planta.mediciones, medicion_id, 'Medición no encontrada')

    if request.method == 'GET':
        return api_ok(_medicion_planta(m))

    if request.method == 'PATCH':
        _aplicar(m, _body(request), CAMPOS_MEDICION_PLANTA)
        _guardar(m)
        return api_ok(_medicion_planta(m))

    if request.method == 'DELETE':
        return _borrar(request, m)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_mediciones_ec(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        return api_ok([_medicion_ec_ser(m) for m in c.mediciones_ec.all()])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_MEDICION_EC)
        m = _guardar(MedicionEC(cultivo=c, creado_por=request.api_user, **datos))
        return api_ok(_medicion_ec_ser(m), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def medicion_ec_detail(request, slug, medicion_id):
    m = _buscar(request.api_cultivo.mediciones_ec, medicion_id, 'Medición EC/pH no encontrada')

    if request.method == 'GET':
        return api_ok(_medicion_ec_ser(m))

    if request.method == 'PATCH':
        _aplicar(m, _body(request), CAMPOS_MEDICION_EC)
        _guardar(m)
        return api_ok(_medicion_ec_ser(m))

    if request.method == 'DELETE':
        return _borrar(request, m)

    return _no_permitido()


# ── Eventos y tareas ──────────────────────────────────────────────────────────

CAMPOS_EVENTO = {
    'tipo': partial(_opcion, opciones=EVENTO_TIPOS),
    'descripcion': partial(_texto, largo=2000, requerido=True),
    'follow_up_fecha': _fecha,
    'follow_up_descripcion': _notas,
    'follow_up_resuelto': _bool,
}

CAMPOS_TAREA = {
    'titulo': partial(_texto, largo=200, requerido=True),
    'descripcion': partial(_texto, largo=1000),
    'prioridad': partial(_opcion, opciones=TAREA_PRIORIDADES, default='normal'),
    'categoria': partial(_opcion, opciones=TAREA_CATEGORIAS, default='observacion'),
    'fecha_objetivo': _fecha,
}


def _plantas_afectadas(cultivo, body):
    return _plantas_por_uuid(cultivo.plantas.activas(), body.get('plantas_afectadas') or [], 'plantas_afectadas')


@csrf_exempt
@require_token
def cultivo_eventos(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        eventos = c.eventos.prefetch_related('plantas_afectadas').all()
        return api_ok([_evento(e) for e in eventos])

    if request.method == 'POST':
        body = _body(request)
        datos = _leer(body, CAMPOS_EVENTO)
        plantas = _plantas_afectadas(c, body)
        e = _guardar(Evento(cultivo=c, creado_por=request.api_user, **datos))
        e.plantas_afectadas.set(plantas)
        return api_ok(_evento(e), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_evento_detail(request, slug, evento_id):
    c = request.api_cultivo
    e = _buscar(c.eventos.prefetch_related('plantas_afectadas'), evento_id, 'Evento no encontrado')

    if request.method == 'GET':
        return api_ok(_evento(e))

    if request.method == 'PATCH':
        body = _body(request)
        _aplicar(e, body, CAMPOS_EVENTO)
        plantas = _plantas_afectadas(c, body) if 'plantas_afectadas' in body else None
        _guardar(e)
        if plantas is not None:
            e.plantas_afectadas.set(plantas)
        return api_ok(_evento(e))

    if request.method == 'DELETE':
        return _borrar(request, e)

    return _no_permitido()


@csrf_exempt
@require_token
def evento_resolver_followup(request, slug, evento_id):
    e = _buscar(request.api_cultivo.eventos, evento_id, 'Evento no encontrado')
    if request.method != 'POST':
        return _no_permitido()
    _limitar_escrituras(request)
    e.follow_up_resuelto = True
    e.save(update_fields=['follow_up_resuelto'])
    return api_ok(_evento(e))


@csrf_exempt
@require_token
def cultivo_tareas(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        qs = c.tareas.all()
        completada_param = request.GET.get('completada')
        if completada_param == 'false':
            qs = qs.filter(completada=False)
        elif completada_param == 'true':
            qs = qs.filter(completada=True)
        return api_ok([_tarea(t) for t in qs])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_TAREA)
        t = _guardar(Tarea(cultivo=c, creado_por=request.api_user, **datos))
        return api_ok(_tarea(t), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def cultivo_tarea_detail(request, slug, tarea_id):
    t = _buscar(request.api_cultivo.tareas, tarea_id, 'Tarea no encontrada')

    if request.method == 'GET':
        return api_ok(_tarea(t))

    if request.method == 'PATCH':
        body = _body(request)
        _aplicar(t, body, CAMPOS_TAREA)
        if 'completada' in body:
            t.completada = _bool(body, 'completada')
            t.completada_en = timezone.now() if t.completada else None
        _guardar(t)
        return api_ok(_tarea(t))

    if request.method == 'DELETE':
        return _borrar(request, t)

    return _no_permitido()


# ── Fotoperiodo ───────────────────────────────────────────────────────────────

# El formato N/M lo valida CambioFotoperiodo.clean() dentro de _guardar.
CAMPOS_FOTOPERIODO = {
    'fotoperiodo': partial(_texto, largo=5, requerido=True),
    'hora_lights_on': partial(_hora, requerido=True),
    'fecha_inicio': partial(_fecha, requerido=True),
    'notas': _notas,
}


@csrf_exempt
@require_token
def cultivo_cambios_fotoperiodo(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        return api_ok([_cambio_fotoperiodo(cf) for cf in c.cambios_fotoperiodo.all()])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_FOTOPERIODO)
        cf = _guardar(CambioFotoperiodo(cultivo=c, **datos))
        return api_ok(_cambio_fotoperiodo(cf), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def cambio_fotoperiodo_detail(request, slug, cf_id):
    cf = _buscar(request.api_cultivo.cambios_fotoperiodo, cf_id, 'Cambio de fotoperiodo no encontrado')

    if request.method == 'GET':
        return api_ok(_cambio_fotoperiodo(cf))

    if request.method == 'PATCH':
        _aplicar(cf, _body(request), CAMPOS_FOTOPERIODO)
        _guardar(cf)
        return api_ok(_cambio_fotoperiodo(cf))

    if request.method == 'DELETE':
        return _borrar(request, cf)

    return _no_permitido()


# ── Canopy ────────────────────────────────────────────────────────────────────

def _canopy_snapshot(snapshot, plantas_qs):
    """Serializa un CanopySnapshot con sus ColaPosicion agrupadas por planta."""
    colas_qs = snapshot.colas.select_related('planta').order_by('planta', 'indice')

    colas_by_planta = {}
    for cp in colas_qs:
        colas_by_planta.setdefault(cp.planta_id, []).append(cp)

    plantas_data = []
    for p in plantas_qs:
        coords = POSICION_TENT_COORDS.get(p.posicion_tent, (0.50, 0.50))
        colas = [
            {'indice': cp.indice, 'x': cp.x, 'y': cp.y}
            for cp in colas_by_planta.get(p.id, [])
        ]
        plantas_data.append({
            'uuid': str(p.uuid),
            'apodo': p.apodo,
            'centro_tent': {'x': coords[0], 'y': coords[1]},
            'colas': colas,
        })

    return {
        'id': snapshot.id,
        'creado_en': snapshot.creado_en.isoformat(),
        'scrog_fill_pct': snapshot.scrog_fill_pct,
        'scrog_cells': snapshot.scrog_cells,
        'notas': snapshot.notas,
        'plantas': plantas_data,
    }


@csrf_exempt
@require_token
def cultivo_canopy(request, slug):
    c = request.api_cultivo
    plantas_qs = c.plantas.filter(archivado=False).order_by('apodo')

    if request.method == 'GET':
        snapshot = c.canopy_snapshots.first()
        if not snapshot:
            return api_ok(None)
        return api_ok(_canopy_snapshot(snapshot, plantas_qs))

    if request.method == 'POST':
        body = _body(request)
        scrog_fill_pct = _entero(body, 'scrog_fill_pct', minimo=0, maximo=100) or 0

        colas_raw = body.get('colas', [])
        if not isinstance(colas_raw, list) or not all(isinstance(item, dict) for item in colas_raw):
            raise ApiInputError('colas debe ser una lista de objetos')
        plantas = _plantas_por_uuid(plantas_qs, [item.get('planta_uuid', '') for item in colas_raw], 'colas')
        colas_validated = []
        for planta, item in zip(plantas, colas_raw):
            indice = _entero(item, 'indice', requerido=True, minimo=0)
            x = _decimal(item, 'x', requerido=True, minimo=0, maximo=1)
            y = _decimal(item, 'y', requerido=True, minimo=0, maximo=1)
            colas_validated.append((planta, indice, float(x), float(y)))

        scrog_cells_raw = body.get('scrog_cells', [])
        scrog_cells = []
        if isinstance(scrog_cells_raw, list):
            celdas = [_entero({'celda': i}, 'celda', requerido=True) for i in scrog_cells_raw]
            scrog_cells = [i for i in celdas if 0 <= i < 36]
            if scrog_cells:
                scrog_fill_pct = round(len(scrog_cells) / 36 * 100)

        snapshot = CanopySnapshot.objects.create(
            cultivo=c,
            scrog_fill_pct=scrog_fill_pct,
            scrog_cells=scrog_cells,
            notas=_notas(body, 'notas'),
        )
        ColaPosicion.objects.bulk_create([
            ColaPosicion(snapshot=snapshot, planta=planta, indice=indice, x=x, y=y)
            for planta, indice, x, y in colas_validated
        ])

        return api_ok(_canopy_snapshot(snapshot, plantas_qs), status=201)

    return _no_permitido()


@require_GET
@require_token
def cultivo_canopy_history(request, slug):
    return api_ok([
        {'id': s.id, 'creado_en': s.creado_en.isoformat(), 'scrog_fill_pct': s.scrog_fill_pct, 'notas': s.notas}
        for s in request.api_cultivo.canopy_snapshots.all()
    ])


@require_GET
@require_token
def cultivo_canopy_detail(request, slug, snapshot_id):
    c = request.api_cultivo
    snapshot = _buscar(c.canopy_snapshots, snapshot_id, 'Snapshot no encontrado')
    plantas_qs = c.plantas.filter(archivado=False).order_by('apodo')
    return api_ok(_canopy_snapshot(snapshot, plantas_qs))


# ── Plantas ───────────────────────────────────────────────────────────────────

CAMPOS_PLANTA = {
    'apodo': partial(_texto, largo=60, requerido=True),
    'strain': partial(_texto, largo=120),
    'posicion_tent': partial(_opcion, opciones=PLANTA_POSICIONES, default='otro'),
    'estado': partial(_opcion, opciones=PLANTA_ESTADOS, default='activa'),
    'dias_flora_estimados': partial(_entero, minimo=0, maximo=SMALLINT_MAX),
    'indica_sativa_ratio': partial(_texto, largo=20),
    'thc_estimado': partial(_decimal, minimo=0, maximo=100),
    'yield_estimado_g': partial(_entero, minimo=0, maximo=SMALLINT_MAX),
    'yield_real_g': partial(_entero, minimo=0, maximo=SMALLINT_MAX),
    'notas_genetica': partial(_texto, largo=2000),
    'archivado': _bool,
}


@csrf_exempt
@require_token
def cultivo_plantas(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        qs = c.plantas.all()
        if request.GET.get('archivado') == 'false':
            qs = qs.filter(archivado=False)
        return api_ok([_planta_full(p) for p in qs])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_PLANTA)
        p = _guardar(Planta(cultivo=c, creado_por=request.api_user, **datos))
        return api_ok(_planta_full(p), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def planta_detail(request, planta_uuid):
    p = request.api_planta

    if request.method == 'GET':
        data = _planta_full(p)
        data['cultivo'] = {'id': p.cultivo.id, 'slug': p.cultivo.slug, 'nombre': p.cultivo.nombre}
        data['mediciones'] = [_medicion_planta(m) for m in p.mediciones.all()]
        data['riegos'] = [
            {**_riego_planta(rp), 'riego_id': rp.riego_id, 'timestamp': rp.riego.timestamp.isoformat()}
            for rp in p.riegos_detalle.select_related('riego').order_by('-riego__timestamp')[:20]
        ]
        return api_ok(data)

    if request.method == 'PATCH':
        _aplicar(p, _body(request), CAMPOS_PLANTA)
        _guardar(p)
        return api_ok(_planta_full(p))

    if request.method == 'DELETE':
        _limitar_escrituras(request)
        uuid_deleted = str(p.uuid)
        if p.eliminar_o_archivar():
            return api_ok({'deleted': uuid_deleted})
        return api_ok({'archived': uuid_deleted})

    return _no_permitido()


# ── Módulo energético ─────────────────────────────────────────────────────────


def _tarifa_vigente(hoy, *, cultivo=None, usuario=None):
    tarifas = tarifas_del_cultivo(cultivo) if cultivo else TarifaElectrica.objects.filter(propietario=usuario)
    if cultivo and usuario and cultivo.propietario_id == usuario.pk:
        tarifas = TarifaElectrica.objects.filter(Q(propietario=usuario) | Q(costos__cultivo=cultivo)).distinct()
    return tarifas.filter(fecha_desde__lte=hoy).order_by('-fecha_desde').first()


def _meses_estimados(c, hoy):
    """Devuelve (tarifas vigentes, desglose mensual estimado) del cultivo."""
    tarifas = list(tarifas_del_cultivo(c).filter(fecha_desde__lte=hoy).order_by('-fecha_desde'))
    costos = list(c.costos_energeticos.select_related('equipo').order_by('fecha_desde'))
    return tarifas, calcular_meses(c.fecha_inicio, costos, tarifas, hoy)


def _totales(meses):
    """(kWh, costo) estimados acumulados."""
    return (
        round(sum(m['kwh_estimado'] for m in meses), 2),
        round(sum(m['costo_estimado'] for m in meses), 2),
    )


def _ser_equipo(e, precio_kwh=None):
    kwh_mes = e.kwh_mes
    d = {
        'id': e.id,
        'nombre': e.nombre,
        'categoria': e.categoria,
        'categoria_display': e.get_categoria_display(),
        'watts': str(e.watts),
        'horas_dia': str(e.horas_dia),
        'kwh_mes': kwh_mes,
        'activo': e.activo,
        'notas': e.notas,
    }
    if precio_kwh is not None:
        d['costo_mes'] = round(kwh_mes * float(precio_kwh), 2)
    return d


def _ser_tarifa(t):
    return {
        'id': t.id,
        'fecha_desde': t.fecha_desde.isoformat(),
        'precio_kwh': str(t.precio_kwh),
        'distribuidora': t.distribuidora,
    }


def _ser_lectura(l):
    return {
        'id': l.id,
        'fecha': l.fecha.isoformat(),
        'kwh_real': str(l.kwh_real),
        'notas': l.notas,
    }


def _ser_costo(ce):
    return {
        'id': ce.id,
        'equipo': _ser_equipo(ce.equipo),
        'tarifa_id': ce.tarifa_id,
        'fecha_desde': ce.fecha_desde.isoformat(),
        'fecha_hasta': ce.fecha_hasta.isoformat() if ce.fecha_hasta else None,
    }


def _exigir_propietario(request, recurso, nombre):
    """Equipos y tarifas solo los modifica su dueño, y no si están en cultivos que no puede editar."""
    if request.method in SAFE_METHODS:
        return
    if recurso.propietario_id != request.api_user.pk:
        raise ApiInputError(f'Solo el propietario puede modificar {nombre}', 403)
    if recurso.costos.exclude(cultivo__in=cultivos_visibles(request.api_user, editar=True)).exists():
        raise ApiInputError(f'No podés modificar {nombre}: se usa en un cultivo que no podés editar', 403)


CAMPOS_EQUIPO = {
    'nombre': partial(_texto, largo=120, requerido=True),
    'categoria': partial(_opcion, opciones=EQUIPO_CATEGORIAS),
    'watts': partial(_decimal, requerido=True, positivo=True),
    'horas_dia': partial(_decimal, requerido=True, positivo=True, maximo=24),
    'activo': partial(_bool, default=True),
    'notas': _notas,
}

CAMPOS_TARIFA = {
    'fecha_desde': partial(_fecha, requerido=True),
    'precio_kwh': partial(_decimal, requerido=True, positivo=True),
    'distribuidora': partial(_texto, largo=100, default='Edesur'),
    'notas': _notas,
}

CAMPOS_LECTURA = {
    'fecha': partial(_fecha, requerido=True),
    'kwh_real': partial(_decimal, requerido=True, minimo=0),
    'notas': _notas,
}


# ── Endpoints equipos ─────────────────────────────────────────────────────────

@csrf_exempt
@require_token
def equipos_list(request):
    if request.method == 'GET':
        equipos = recursos_visibles(Equipo, request.api_user)
        tarifa = _tarifa_vigente(timezone.localdate(), usuario=request.api_user)
        precio_kwh = tarifa.precio_kwh if tarifa else None
        return api_ok([_ser_equipo(e, precio_kwh) for e in equipos])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_EQUIPO)
        equipo = _guardar(Equipo(propietario=request.api_user, **datos))
        return api_ok(_ser_equipo(equipo), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def equipo_detail(request, equipo_id):
    equipo = _buscar(recursos_visibles(Equipo, request.api_user), equipo_id, 'Equipo no encontrado')
    _exigir_propietario(request, equipo, 'este equipo')

    if request.method == 'GET':
        return api_ok(_ser_equipo(equipo))

    if request.method == 'PATCH':
        _aplicar(equipo, _body(request), CAMPOS_EQUIPO)
        _guardar(equipo)
        return api_ok(_ser_equipo(equipo))

    if request.method == 'DELETE':
        if equipo.costos.exists():
            _limitar_escrituras(request)
            raise ApiInputError('No se puede eliminar un equipo con historial de costos; desactivalo', 409)
        return _borrar(request, equipo)

    return _no_permitido()


# ── Endpoints costos ──────────────────────────────────────────────────────────

@require_GET
@require_token
def cultivo_costos(request, slug):
    c = request.api_cultivo
    hoy = timezone.localdate()
    tarifa = _tarifa_vigente(hoy, cultivo=c)
    precio_kwh = tarifa.precio_kwh if tarifa else None

    costos_actuales = list(
        c.costos_energeticos.select_related('equipo', 'tarifa').filter(fecha_hasta__isnull=True)
    )
    equipos_data = []
    total_kwh_mes = 0.0
    total_costo_mes = 0.0
    for ce in costos_actuales:
        equipos_data.append(_ser_equipo(ce.equipo, precio_kwh))
        total_kwh_mes += ce.equipo.kwh_mes
        if precio_kwh:
            total_costo_mes += ce.equipo.kwh_mes * float(precio_kwh)

    _, meses = _meses_estimados(c, hoy)
    kwh_acumulado, costo_acumulado = _totales(meses)

    yield_total = sum(
        p.yield_estimado_g for p in c.plantas.filter(archivado=False)
        if p.yield_estimado_g
    )
    costo_por_gramo = round(costo_acumulado / yield_total, 2) if yield_total > 0 else None

    return api_ok({
        'cultivo': c.slug,
        'tarifa_vigente': _ser_tarifa(tarifa) if tarifa else None,
        'ciclo': ciclo_activo(c, hoy),
        'equipos': equipos_data,
        'totales': {
            'kwh_mes': round(total_kwh_mes, 2),
            'costo_mes': round(total_costo_mes, 2),
            'kwh_acumulado': kwh_acumulado,
            'costo_acumulado': costo_acumulado,
            'costo_por_gramo_estimado': costo_por_gramo,
        },
    })


@require_GET
@require_token
def cultivo_costos_historico(request, slug):
    c = request.api_cultivo
    _, meses = _meses_estimados(c, timezone.localdate())
    kwh_total, costo_total = _totales(meses)
    return api_ok({
        'cultivo': c.slug,
        'fecha_inicio': c.fecha_inicio.isoformat(),
        'meses': meses,
        'totales': {
            'kwh_estimado': kwh_total,
            'costo_estimado': costo_total,
        },
    })


@require_GET
@require_token
def cultivo_costos_comparacion(request, slug):
    c = request.api_cultivo
    lecturas = list(c.lecturas_medidor.all())
    if not lecturas:
        return api_error('No hay lecturas de medidor cargadas para este cultivo', 404)

    tarifas, meses = _meses_estimados(c, timezone.localdate())
    kwh_estimado, costo_estimado = _totales(meses)

    kwh_real = round(float(sum(l.kwh_real for l in lecturas)), 2)
    tarifa_actual = tarifas[0] if tarifas else None
    costo_real = round(kwh_real * float(tarifa_actual.precio_kwh), 2) if tarifa_actual else None

    variacion_pct = None
    alerta = False
    if kwh_estimado > 0:
        variacion_pct = round((kwh_real - kwh_estimado) / kwh_estimado * 100, 1)
        alerta = kwh_real > kwh_estimado * 1.15

    return api_ok({
        'cultivo': c.slug,
        'kwh_estimado': kwh_estimado,
        'kwh_real': kwh_real,
        'costo_estimado': costo_estimado,
        'costo_real': costo_real,
        'variacion_pct': variacion_pct,
        'alerta': alerta,
        'lecturas': [_ser_lectura(l) for l in lecturas],
    })


@csrf_exempt
@require_token
def cultivo_lecturas_medidor(request, slug):
    c = request.api_cultivo

    if request.method == 'GET':
        return api_ok([_ser_lectura(l) for l in c.lecturas_medidor.all()])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_LECTURA)
        l = _guardar(LecturaMedidor(cultivo=c, **datos))
        return api_ok(_ser_lectura(l), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def lectura_medidor_detail(request, slug, lectura_id):
    l = _buscar(request.api_cultivo.lecturas_medidor, lectura_id, 'Lectura no encontrada')

    if request.method == 'GET':
        return api_ok(_ser_lectura(l))

    if request.method == 'PATCH':
        _aplicar(l, _body(request), CAMPOS_LECTURA)
        _guardar(l)
        return api_ok(_ser_lectura(l))

    if request.method == 'DELETE':
        return _borrar(request, l)

    return _no_permitido()


# ── Endpoints tarifas ─────────────────────────────────────────────────────────

@csrf_exempt
@require_token
def tarifas_list(request):
    if request.method == 'GET':
        return api_ok([_ser_tarifa(t) for t in recursos_visibles(TarifaElectrica, request.api_user)])

    if request.method == 'POST':
        datos = _leer(_body(request), CAMPOS_TARIFA)
        tarifa = _guardar(TarifaElectrica(propietario=request.api_user, **datos))
        return api_ok(_ser_tarifa(tarifa), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def tarifa_detail(request, tarifa_id):
    tarifa = _buscar(recursos_visibles(TarifaElectrica, request.api_user), tarifa_id, 'Tarifa no encontrada')
    _exigir_propietario(request, tarifa, 'esta tarifa')

    if request.method == 'GET':
        return api_ok(_ser_tarifa(tarifa))

    if request.method == 'PATCH':
        _aplicar(tarifa, _body(request), CAMPOS_TARIFA)
        _guardar(tarifa)
        return api_ok(_ser_tarifa(tarifa))

    if request.method == 'DELETE':
        return _borrar(
            request, tarifa, en_uso='No se puede eliminar: hay costos energéticos que referencian esta tarifa',
        )

    return _no_permitido()


# ── Endpoints costos energéticos por cultivo (asignación de equipos) ──────────

@csrf_exempt
@require_token
def cultivo_costos_equipos(request, slug):
    """GET lista / POST asigna un Equipo a este cultivo con vigencia desde una fecha."""
    c = request.api_cultivo

    if request.method == 'GET':
        return api_ok([_ser_costo(ce) for ce in c.costos_energeticos.select_related('equipo').all()])

    if request.method == 'POST':
        body = _body(request)
        equipo_id = _entero(body, 'equipo_id', requerido=True)
        equipo = equipos_asignables(request.api_user, c).filter(pk=equipo_id).first()
        if equipo is None:
            raise ApiInputError('equipo_id es requerido y debe existir')
        fecha_desde = _fecha(body, 'fecha_desde', requerido=True)

        tarifa = _tarifa_vigente(timezone.localdate(), cultivo=c, usuario=request.api_user)
        if not tarifa:
            raise ApiInputError('No hay tarifa eléctrica cargada. Creá una en /api/v1/tarifas/ primero')

        ce = _guardar(CostoEnergetico(cultivo=c, equipo=equipo, tarifa=tarifa, fecha_desde=fecha_desde))
        return api_ok(_ser_costo(ce), status=201)

    return _no_permitido()


@csrf_exempt
@require_token
def costo_detail(request, slug, costo_id):
    """PATCH acepta fecha_hasta para dar de baja un equipo del cultivo (fin de vigencia)."""
    ce = _buscar(request.api_cultivo.costos_energeticos.select_related('equipo'), costo_id, 'Costo energético no encontrado')

    if request.method == 'GET':
        return api_ok(_ser_costo(ce))

    if request.method == 'PATCH':
        _aplicar(ce, _body(request), {'fecha_hasta': _fecha})
        _guardar(ce)
        return api_ok(_ser_costo(ce))

    if request.method == 'DELETE':
        return _borrar(request, ce)

    return _no_permitido()


# ── Endpoints de referencia (solo lectura) ────────────────────────────────────

@require_GET
@require_token
def nutrientes_list(request):
    return api_ok([
        {
            'id': n.id, 'nombre': n.nombre, 'marca': n.marca, 'npk': n.npk,
            'etapa_recomendada': n.etapa_recomendada,
            'etapa_recomendada_display': n.get_etapa_recomendada_display(),
            'dosis_recomendada_min': _num(n.dosis_recomendada_min),
            'dosis_recomendada_max': _num(n.dosis_recomendada_max),
        }
        for n in Nutriente.objects.all()
    ])


@require_GET
@require_token
def parametros_ideales_list(request):
    return api_ok([
        {
            'etapa': p.etapa, 'etapa_display': p.get_etapa_display(),
            'temp_min': str(p.temp_min), 'temp_max': str(p.temp_max),
            'hr_min': str(p.hr_min), 'hr_max': str(p.hr_max),
            'ph_min': str(p.ph_min), 'ph_max': str(p.ph_max),
            'ec_min': _num(p.ec_min),
            'ec_max': _num(p.ec_max),
            'vpd_min': str(p.vpd_min), 'vpd_max': str(p.vpd_max),
            'horas_luz': p.horas_luz,
            'distancia_luz_min': p.distancia_luz_min,
            'distancia_luz_max': p.distancia_luz_max,
        }
        for p in ParametroIdeal.objects.all()
    ])
