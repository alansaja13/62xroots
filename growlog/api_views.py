import hashlib
import json
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.core.cache import cache
from django.db import IntegrityError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    APIToken, CambioFotoperiodo, CanopySnapshot, ColaPosicion,
    CostoEnergetico, Cultivo, Equipo, Evento, LecturaMedidor,
    MedicionAmbiente, MedicionEC, MedicionPlanta, Nutriente, NutrienteAplicado,
    ParametroIdeal, Planta, POSICION_TENT_COORDS, Riego, RiegoPlanta, Tarea, TarifaElectrica,
)

EVENTO_TIPOS = {c[0] for c in Evento.TIPO_CHOICES}
TAREA_PRIORIDADES = {c[0] for c in Tarea.PRIORIDAD_CHOICES}
TAREA_CATEGORIAS = {c[0] for c in Tarea.CATEGORIA_CHOICES}
PLANTA_POSICIONES = {c[0] for c in Planta.POSICION_CHOICES}
PLANTA_ESTADOS = {c[0] for c in Planta.ESTADO_CHOICES}
MEDICION_EC_TIPOS = {c[0] for c in MedicionEC.TIPO_CHOICES}

# ── Helpers ──────────────────────────────────────────────────────────────────

def api_ok(data, status=200):
    return JsonResponse({'ok': True, 'data': data}, status=status)


def api_error(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


def require_token(view_func):
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
        request.api_user = token.user
        return view_func(request, *args, **kwargs)
    return wrapper


def _parse_json_body(request):
    """Parsea el body JSON y devuelve (data, error_response)."""
    try:
        return json.loads(request.body or '{}'), None
    except json.JSONDecodeError:
        return None, api_error('Invalid JSON body', 400)


def _get_cultivo(slug, user):
    """Devuelve (cultivo, error_response) — scoped al usuario."""
    try:
        return Cultivo.objects.get(slug=slug, creado_por=user), None
    except Cultivo.DoesNotExist:
        return None, api_error('Cultivo no encontrado', 404)


def _write_rate_limit(request):
    """60 writes por hora por token. Devuelve error_response o None."""
    token_hash = hashlib.sha256(
        request.META.get('HTTP_AUTHORIZATION', '')[7:].strip().encode()
    ).hexdigest()
    key = f"api_writes_{token_hash}"
    count = cache.get(key, 0)
    if count >= 60:
        return api_error('Rate limit exceeded — 60 writes/hour', 429)
    cache.set(key, count + 1, timeout=3600)
    return None


# ── Serializers ───────────────────────────────────────────────────────────────

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
        'thc_estimado': str(p.thc_estimado) if p.thc_estimado is not None else None,
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
        'ph_runoff': str(rp.ph_runoff) if rp.ph_runoff is not None else None,
        'ec_runoff': str(rp.ec_runoff) if rp.ec_runoff is not None else None,
        'notas': rp.notas,
    }


def _riego(r, include_nutrientes=True, include_plantas=True):
    d = {
        'id': r.id,
        'timestamp': r.timestamp.isoformat(),
        'volumen_total_ml': r.volumen_total_ml,
        'volumen_por_planta_ml': r.volumen_por_planta_ml,
        'ph_agua': str(r.ph_agua) if r.ph_agua is not None else None,
        'ec_solucion': str(r.ec_solucion) if r.ec_solucion is not None else None,
        'buscar_runoff': r.buscar_runoff,
        'runoff_observado': r.runoff_observado,
        'notas': r.notas,
    }
    if include_nutrientes:
        d['nutrientes_aplicados'] = [
            {'id': na.id, 'nutriente_id': na.nutriente_id, 'nutriente': str(na.nutriente), 'dosis_g_por_litro': str(na.dosis_g_por_litro)}
            for na in r.nutrientes_aplicados.select_related('nutriente').all()
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
        'altura_cm': str(m.altura_cm) if m.altura_cm is not None else None,
        'nudos_count': m.nudos_count,
        'ancho_canopy_cm': str(m.ancho_canopy_cm) if m.ancho_canopy_cm is not None else None,
        'aspecto_general': m.aspecto_general,
        'sintomas': m.sintomas,
    }


# ── Read endpoints ────────────────────────────────────────────────────────────

@require_GET
@require_token
def cultivos_list(request):
    cultivos = Cultivo.objects.filter(archivado=False, creado_por=request.api_user)
    return api_ok([_cultivo_base(c) for c in cultivos])


@require_GET
@require_token
def cultivo_detail(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
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


@csrf_exempt
@require_token
def cultivo_riegos(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        riegos = c.riegos.prefetch_related('nutrientes_aplicados__nutriente', 'detalle_plantas__planta').all()
        return api_ok([_riego(r) for r in riegos])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        ph_agua = None
        if body.get('ph_agua') is not None:
            try:
                ph_agua = Decimal(str(body['ph_agua']))
                if not (0 <= float(ph_agua) <= 14):
                    return api_error('ph_agua fuera de rango (0-14)')
            except (InvalidOperation, TypeError):
                return api_error('ph_agua debe ser un número')

        ec_solucion = None
        if body.get('ec_solucion') is not None:
            try:
                ec_solucion = Decimal(str(body['ec_solucion']))
                if float(ec_solucion) < 0:
                    return api_error('ec_solucion debe ser positivo')
            except (InvalidOperation, TypeError):
                return api_error('ec_solucion debe ser un número')

        buscar_runoff = bool(body.get('buscar_runoff', False))
        notas = str(body.get('notas', ''))[:500]

        # detalle_plantas: [{planta_uuid, volumen_ml, runoff_observado?, ph_runoff?, ec_runoff?, notas?}, ...]
        # volumen_total_ml se calcula como la suma de estas filas — es requerido al menos una.
        detalle_raw = body.get('detalle_plantas', [])
        if not isinstance(detalle_raw, list) or not detalle_raw:
            return api_error('detalle_plantas es requerido: lista de {planta_uuid, volumen_ml}')
        plantas_map = {str(p.uuid): p for p in c.plantas.filter(archivado=False)}
        detalle_validated = []
        for item in detalle_raw:
            uuid_str = str(item.get('planta_uuid', ''))
            planta = plantas_map.get(uuid_str)
            if not planta:
                return api_error(f'planta_uuid desconocido o archivado: {uuid_str}')
            try:
                volumen_ml = int(item['volumen_ml'])
                if volumen_ml <= 0:
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                return api_error(f'volumen_ml requerido y positivo para planta {uuid_str}')
            ph_runoff = None
            if item.get('ph_runoff') is not None:
                try:
                    ph_runoff = Decimal(str(item['ph_runoff']))
                except InvalidOperation:
                    return api_error(f'ph_runoff inválido para planta {uuid_str}')
            ec_runoff = None
            if item.get('ec_runoff') is not None:
                try:
                    ec_runoff = Decimal(str(item['ec_runoff']))
                except InvalidOperation:
                    return api_error(f'ec_runoff inválido para planta {uuid_str}')
            detalle_validated.append({
                'planta': planta, 'volumen_ml': volumen_ml,
                'runoff_observado': bool(item.get('runoff_observado', False)),
                'ph_runoff': ph_runoff, 'ec_runoff': ec_runoff,
                'notas': str(item.get('notas', ''))[:500],
            })

        nutrientes_raw = body.get('nutrientes', [])
        if not isinstance(nutrientes_raw, list):
            return api_error('nutrientes debe ser una lista')
        nutrientes_validated = []
        for item in nutrientes_raw:
            try:
                nutriente_id = int(item['nutriente_id'])
                dosis = Decimal(str(item['dosis_g_por_litro']))
            except (KeyError, ValueError, TypeError, InvalidOperation):
                return api_error('Cada nutriente requiere nutriente_id (int) y dosis_g_por_litro (float)')
            try:
                nutriente = Nutriente.objects.get(pk=nutriente_id)
            except Nutriente.DoesNotExist:
                return api_error(f'nutriente_id {nutriente_id} no existe')
            nutrientes_validated.append((nutriente, dosis))

        riego = Riego.objects.create(
            cultivo=c,
            volumen_total_ml=sum(d['volumen_ml'] for d in detalle_validated),
            ph_agua=ph_agua,
            ec_solucion=ec_solucion,
            buscar_runoff=buscar_runoff,
            notas=notas,
            creado_por=request.api_user,
        )
        RiegoPlanta.objects.bulk_create([RiegoPlanta(riego=riego, **d) for d in detalle_validated])
        if nutrientes_validated:
            NutrienteAplicado.objects.bulk_create([
                NutrienteAplicado(riego=riego, nutriente=n, dosis_g_por_litro=d)
                for n, d in nutrientes_validated
            ])
        return api_ok(_riego(riego), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_riego_detail(request, slug, riego_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    try:
        riego = c.riegos.prefetch_related('nutrientes_aplicados__nutriente', 'detalle_plantas__planta').get(pk=riego_id)
    except Riego.DoesNotExist:
        return api_error('Riego no encontrado', 404)

    if request.method == 'GET':
        return api_ok(_riego(riego))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'ph_agua' in body:
            if body['ph_agua'] is None:
                riego.ph_agua = None
            else:
                try:
                    ph_agua = Decimal(str(body['ph_agua']))
                    if not (0 <= float(ph_agua) <= 14):
                        return api_error('ph_agua fuera de rango (0-14)')
                    riego.ph_agua = ph_agua
                except InvalidOperation:
                    return api_error('ph_agua debe ser un número')

        if 'ec_solucion' in body:
            if body['ec_solucion'] is None:
                riego.ec_solucion = None
            else:
                try:
                    ec_solucion = Decimal(str(body['ec_solucion']))
                    if float(ec_solucion) < 0:
                        return api_error('ec_solucion debe ser positivo')
                    riego.ec_solucion = ec_solucion
                except InvalidOperation:
                    return api_error('ec_solucion debe ser un número')

        if 'buscar_runoff' in body:
            riego.buscar_runoff = bool(body['buscar_runoff'])
        if 'notas' in body:
            riego.notas = str(body['notas'])[:500]

        riego.save()
        return api_ok(_riego(riego))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        riego_id_deleted = riego.id
        riego.delete()
        return api_ok({'deleted': riego_id_deleted})

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_riego_plantas(request, slug, riego_id):
    """GET lista / POST agrega una fila de detalle por planta a un riego existente."""
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        riego = c.riegos.get(pk=riego_id)
    except Riego.DoesNotExist:
        return api_error('Riego no encontrado', 404)

    if request.method == 'GET':
        return api_ok([_riego_planta(rp) for rp in riego.detalle_plantas.select_related('planta').all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        uuid_str = str(body.get('planta_uuid', ''))
        try:
            planta = c.plantas.get(uuid=uuid_str, archivado=False)
        except Planta.DoesNotExist:
            return api_error(f'planta_uuid desconocido o archivado: {uuid_str}')
        if riego.detalle_plantas.filter(planta=planta).exists():
            return api_error('Esa planta ya tiene un detalle en este riego — usá PATCH para modificarlo')
        try:
            volumen_ml = int(body['volumen_ml'])
            if volumen_ml <= 0:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            return api_error('volumen_ml es requerido y debe ser entero positivo')

        ph_runoff = None
        if body.get('ph_runoff') is not None:
            try:
                ph_runoff = Decimal(str(body['ph_runoff']))
            except InvalidOperation:
                return api_error('ph_runoff debe ser un número')
        ec_runoff = None
        if body.get('ec_runoff') is not None:
            try:
                ec_runoff = Decimal(str(body['ec_runoff']))
            except InvalidOperation:
                return api_error('ec_runoff debe ser un número')

        rp = RiegoPlanta.objects.create(
            riego=riego, planta=planta, volumen_ml=volumen_ml,
            runoff_observado=bool(body.get('runoff_observado', False)),
            ph_runoff=ph_runoff, ec_runoff=ec_runoff,
            notas=str(body.get('notas', ''))[:500],
        )
        riego.volumen_total_ml = sum(riego.detalle_plantas.values_list('volumen_ml', flat=True))
        riego.save(update_fields=['volumen_total_ml'])
        return api_ok(_riego_planta(rp), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_riego_nutrientes(request, slug, riego_id):
    """GET lista / POST agrega un nutriente aplicado a un riego existente."""
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        riego = c.riegos.get(pk=riego_id)
    except Riego.DoesNotExist:
        return api_error('Riego no encontrado', 404)

    if request.method == 'GET':
        return api_ok([
            {'id': na.id, 'nutriente_id': na.nutriente_id, 'nutriente': str(na.nutriente), 'dosis_g_por_litro': str(na.dosis_g_por_litro)}
            for na in riego.nutrientes_aplicados.select_related('nutriente').all()
        ])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err
        try:
            nutriente_id = int(body['nutriente_id'])
            dosis = Decimal(str(body['dosis_g_por_litro']))
        except (KeyError, ValueError, TypeError, InvalidOperation):
            return api_error('nutriente_id (int) y dosis_g_por_litro (float) son requeridos')
        try:
            nutriente = Nutriente.objects.get(pk=nutriente_id)
        except Nutriente.DoesNotExist:
            return api_error(f'nutriente_id {nutriente_id} no existe')

        na = NutrienteAplicado.objects.create(riego=riego, nutriente=nutriente, dosis_g_por_litro=dosis)
        return api_ok({'id': na.id, 'nutriente_id': na.nutriente_id, 'nutriente': str(na.nutriente), 'dosis_g_por_litro': str(na.dosis_g_por_litro)}, status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def riego_planta_detail(request, slug, riego_id, rp_id):
    """PATCH/DELETE de una fila de detalle por planta dentro de un riego.
    Actualizar volumen_ml re-sincroniza Riego.volumen_total_ml."""
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        riego = c.riegos.get(pk=riego_id)
    except Riego.DoesNotExist:
        return api_error('Riego no encontrado', 404)
    try:
        rp = riego.detalle_plantas.select_related('planta').get(pk=rp_id)
    except RiegoPlanta.DoesNotExist:
        return api_error('Detalle de planta no encontrado', 404)

    if request.method == 'GET':
        return api_ok(_riego_planta(rp))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'volumen_ml' in body:
            try:
                volumen_ml = int(body['volumen_ml'])
                if volumen_ml <= 0:
                    raise ValueError
                rp.volumen_ml = volumen_ml
            except (ValueError, TypeError):
                return api_error('volumen_ml debe ser entero positivo')
        if 'runoff_observado' in body:
            rp.runoff_observado = bool(body['runoff_observado'])
        if 'ph_runoff' in body:
            if body['ph_runoff'] is None:
                rp.ph_runoff = None
            else:
                try:
                    rp.ph_runoff = Decimal(str(body['ph_runoff']))
                except InvalidOperation:
                    return api_error('ph_runoff debe ser un número')
        if 'ec_runoff' in body:
            if body['ec_runoff'] is None:
                rp.ec_runoff = None
            else:
                try:
                    rp.ec_runoff = Decimal(str(body['ec_runoff']))
                except InvalidOperation:
                    return api_error('ec_runoff debe ser un número')
        if 'notas' in body:
            rp.notas = str(body['notas'])[:500]

        rp.save()
        riego.volumen_total_ml = sum(riego.detalle_plantas.values_list('volumen_ml', flat=True))
        riego.save(update_fields=['volumen_total_ml'])
        return api_ok(_riego_planta(rp))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        if riego.detalle_plantas.count() <= 1:
            return api_error('No se puede eliminar la última planta del riego — eliminá el riego completo en su lugar.')
        rp_id_deleted = rp.id
        rp.delete()
        riego.volumen_total_ml = sum(riego.detalle_plantas.values_list('volumen_ml', flat=True))
        riego.save(update_fields=['volumen_total_ml'])
        return api_ok({'deleted': rp_id_deleted})

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def riego_nutriente_detail(request, slug, riego_id, na_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        riego = c.riegos.get(pk=riego_id)
    except Riego.DoesNotExist:
        return api_error('Riego no encontrado', 404)
    try:
        na = riego.nutrientes_aplicados.select_related('nutriente').get(pk=na_id)
    except NutrienteAplicado.DoesNotExist:
        return api_error('Nutriente aplicado no encontrado', 404)

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        na_id_deleted = na.id
        na.delete()
        return api_ok({'deleted': na_id_deleted})

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_mediciones(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        return api_ok([_medicion(m) for m in c.mediciones.all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        # Validación
        try:
            temp = Decimal(str(body.get('temperatura_c', '')))
            hr = Decimal(str(body.get('humedad_relativa', '')))
        except (InvalidOperation, TypeError):
            return api_error('temperatura_c y humedad_relativa son requeridos y deben ser números')

        if not (0 <= float(temp) <= 60):
            return api_error('temperatura_c fuera de rango (0–60°C)')
        if not (0 <= float(hr) <= 100):
            return api_error('humedad_relativa fuera de rango (0–100%)')

        m = MedicionAmbiente.objects.create(
            cultivo=c,
            temperatura_c=temp,
            humedad_relativa=hr,
            notas=str(body.get('notas', ''))[:500],
            creado_por=request.api_user,
        )
        return api_ok(_medicion(m), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_medicion_detail(request, slug, medicion_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        m = c.mediciones.get(pk=medicion_id)
    except MedicionAmbiente.DoesNotExist:
        return api_error('Medición no encontrada', 404)

    if request.method == 'GET':
        return api_ok(_medicion(m))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'temperatura_c' in body:
            try:
                temp = Decimal(str(body['temperatura_c']))
                if not (0 <= float(temp) <= 60):
                    return api_error('temperatura_c fuera de rango (0–60°C)')
                m.temperatura_c = temp
            except InvalidOperation:
                return api_error('temperatura_c debe ser un número')
        if 'humedad_relativa' in body:
            try:
                hr = Decimal(str(body['humedad_relativa']))
                if not (0 <= float(hr) <= 100):
                    return api_error('humedad_relativa fuera de rango (0–100%)')
                m.humedad_relativa = hr
            except InvalidOperation:
                return api_error('humedad_relativa debe ser un número')
        if 'notas' in body:
            m.notas = str(body['notas'])[:500]

        m.save()
        return api_ok(_medicion(m))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        medicion_id_deleted = m.id
        m.delete()
        return api_ok({'deleted': medicion_id_deleted})

    return api_error('Method not allowed', 405)


ASPECTO_CHOICES = {c[0] for c in MedicionPlanta.ASPECTO_CHOICES}


@csrf_exempt
@require_token
def planta_mediciones(request, planta_uuid):
    """GET lista / POST crea una MedicionPlanta. La foto no se acepta por este
    endpoint JSON — usar la interfaz web para subir fotos."""
    try:
        p = Planta.objects.get(uuid=planta_uuid, cultivo__creado_por=request.api_user)
    except Planta.DoesNotExist:
        return api_error('Planta no encontrada', 404)

    if request.method == 'GET':
        return api_ok([_medicion_planta(m) for m in p.mediciones.all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        fecha = timezone.localdate()
        if body.get('fecha'):
            try:
                from datetime import date
                fecha = date.fromisoformat(body['fecha'])
            except ValueError:
                return api_error('fecha debe ser YYYY-MM-DD')

        aspecto_general = body.get('aspecto_general', 'bueno')
        if aspecto_general not in ASPECTO_CHOICES:
            return api_error(f'aspecto_general inválido. Opciones: {sorted(ASPECTO_CHOICES)}')

        def _dec(key):
            if body.get(key) is None:
                return None, None
            try:
                return Decimal(str(body[key])), None
            except InvalidOperation:
                return None, api_error(f'{key} debe ser un número')

        altura_cm, e1 = _dec('altura_cm')
        if e1:
            return e1
        ancho_canopy_cm, e2 = _dec('ancho_canopy_cm')
        if e2:
            return e2

        m = MedicionPlanta.objects.create(
            planta=p, fecha=fecha,
            altura_cm=altura_cm,
            nudos_count=body.get('nudos_count'),
            ancho_canopy_cm=ancho_canopy_cm,
            aspecto_general=aspecto_general,
            sintomas=str(body.get('sintomas', ''))[:2000],
            creado_por=request.api_user,
        )
        return api_ok(_medicion_planta(m), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def medicion_planta_detail(request, planta_uuid, medicion_id):
    try:
        p = Planta.objects.get(uuid=planta_uuid, cultivo__creado_por=request.api_user)
    except Planta.DoesNotExist:
        return api_error('Planta no encontrada', 404)
    try:
        m = p.mediciones.get(pk=medicion_id)
    except MedicionPlanta.DoesNotExist:
        return api_error('Medición no encontrada', 404)

    if request.method == 'GET':
        return api_ok(_medicion_planta(m))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'fecha' in body:
            try:
                from datetime import date
                m.fecha = date.fromisoformat(body['fecha'])
            except (ValueError, TypeError):
                return api_error('fecha debe ser YYYY-MM-DD')
        if 'altura_cm' in body:
            if body['altura_cm'] is None:
                m.altura_cm = None
            else:
                try:
                    m.altura_cm = Decimal(str(body['altura_cm']))
                except InvalidOperation:
                    return api_error('altura_cm debe ser un número')
        if 'nudos_count' in body:
            m.nudos_count = body['nudos_count']
        if 'ancho_canopy_cm' in body:
            if body['ancho_canopy_cm'] is None:
                m.ancho_canopy_cm = None
            else:
                try:
                    m.ancho_canopy_cm = Decimal(str(body['ancho_canopy_cm']))
                except InvalidOperation:
                    return api_error('ancho_canopy_cm debe ser un número')
        if 'aspecto_general' in body:
            if body['aspecto_general'] not in ASPECTO_CHOICES:
                return api_error(f'aspecto_general inválido. Opciones: {sorted(ASPECTO_CHOICES)}')
            m.aspecto_general = body['aspecto_general']
        if 'sintomas' in body:
            m.sintomas = str(body['sintomas'])[:2000]

        m.save()
        return api_ok(_medicion_planta(m))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        medicion_id_deleted = m.id
        m.delete()
        return api_ok({'deleted': medicion_id_deleted})

    return api_error('Method not allowed', 405)


def _medicion_ec_ser(m):
    return {
        'id': m.id,
        'timestamp': m.timestamp.isoformat(),
        'tipo': m.tipo,
        'tipo_display': m.get_tipo_display(),
        'ph': str(m.ph) if m.ph is not None else None,
        'ec': str(m.ec) if m.ec is not None else None,
        'temp_agua': str(m.temp_agua) if m.temp_agua is not None else None,
        'notas': m.notas,
    }


@csrf_exempt
@require_token
def cultivo_mediciones_ec(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        return api_ok([_medicion_ec_ser(m) for m in c.mediciones_ec.all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        tipo = body.get('tipo', 'solucion')
        if tipo not in MEDICION_EC_TIPOS:
            return api_error(f'tipo inválido. Opciones: {sorted(MEDICION_EC_TIPOS)}')

        def _dec(key, lo=None, hi=None):
            if body.get(key) is None:
                return None, None
            try:
                v = Decimal(str(body[key]))
                if lo is not None and not (lo <= float(v) <= hi):
                    return None, api_error(f'{key} fuera de rango ({lo}-{hi})')
                return v, None
            except InvalidOperation:
                return None, api_error(f'{key} debe ser un número')

        ph, e1 = _dec('ph', 0, 14)
        if e1:
            return e1
        ec, e2 = _dec('ec')
        if e2:
            return e2
        temp_agua, e3 = _dec('temp_agua')
        if e3:
            return e3

        m = MedicionEC.objects.create(
            cultivo=c, tipo=tipo, ph=ph, ec=ec, temp_agua=temp_agua,
            notas=str(body.get('notas', ''))[:500],
            creado_por=request.api_user,
        )
        return api_ok(_medicion_ec_ser(m), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def medicion_ec_detail(request, slug, medicion_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        m = c.mediciones_ec.get(pk=medicion_id)
    except MedicionEC.DoesNotExist:
        return api_error('Medición EC/pH no encontrada', 404)

    if request.method == 'GET':
        return api_ok(_medicion_ec_ser(m))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'tipo' in body:
            if body['tipo'] not in MEDICION_EC_TIPOS:
                return api_error(f'tipo inválido. Opciones: {sorted(MEDICION_EC_TIPOS)}')
            m.tipo = body['tipo']
        for key, lo, hi in (('ph', 0, 14), ('ec', None, None), ('temp_agua', None, None)):
            if key in body:
                if body[key] is None:
                    setattr(m, key, None)
                else:
                    try:
                        v = Decimal(str(body[key]))
                        if lo is not None and not (lo <= float(v) <= hi):
                            return api_error(f'{key} fuera de rango ({lo}-{hi})')
                        setattr(m, key, v)
                    except InvalidOperation:
                        return api_error(f'{key} debe ser un número')
        if 'notas' in body:
            m.notas = str(body['notas'])[:500]

        m.save()
        return api_ok(_medicion_ec_ser(m))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        medicion_id_deleted = m.id
        m.delete()
        return api_ok({'deleted': medicion_id_deleted})

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_eventos(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        eventos = c.eventos.prefetch_related('plantas_afectadas').all()
        return api_ok([_evento(e) for e in eventos])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        tipo = body.get('tipo', '')
        descripcion = str(body.get('descripcion', '')).strip()

        if tipo not in EVENTO_TIPOS:
            return api_error(f'tipo inválido. Opciones: {sorted(EVENTO_TIPOS)}')
        if not descripcion:
            return api_error('descripcion es requerida')
        if len(descripcion) > 2000:
            return api_error('descripcion demasiado larga (máx 2000 caracteres)')

        follow_up_fecha = None
        if body.get('follow_up_fecha'):
            try:
                from datetime import date
                follow_up_fecha = date.fromisoformat(body['follow_up_fecha'])
            except ValueError:
                return api_error('follow_up_fecha debe ser YYYY-MM-DD')

        plantas_afectadas = []
        plantas_uuids = body.get('plantas_afectadas', [])
        if plantas_uuids:
            if not isinstance(plantas_uuids, list):
                return api_error('plantas_afectadas debe ser una lista de uuids')
            plantas_map = {str(p.uuid): p for p in c.plantas.all()}
            for uuid_str in plantas_uuids:
                planta = plantas_map.get(str(uuid_str))
                if not planta:
                    return api_error(f'planta_uuid desconocido: {uuid_str}')
                plantas_afectadas.append(planta)

        e = Evento.objects.create(
            cultivo=c,
            tipo=tipo,
            descripcion=descripcion,
            follow_up_fecha=follow_up_fecha,
            follow_up_descripcion=str(body.get('follow_up_descripcion', ''))[:500],
            creado_por=request.api_user,
        )
        if plantas_afectadas:
            e.plantas_afectadas.set(plantas_afectadas)
        return api_ok(_evento(e), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_evento_detail(request, slug, evento_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        e = c.eventos.prefetch_related('plantas_afectadas').get(pk=evento_id)
    except Evento.DoesNotExist:
        return api_error('Evento no encontrado', 404)

    if request.method == 'GET':
        return api_ok(_evento(e))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'tipo' in body:
            if body['tipo'] not in EVENTO_TIPOS:
                return api_error(f'tipo inválido. Opciones: {sorted(EVENTO_TIPOS)}')
            e.tipo = body['tipo']
        if 'descripcion' in body:
            descripcion = str(body['descripcion']).strip()
            if not descripcion:
                return api_error('descripcion no puede estar vacía')
            if len(descripcion) > 2000:
                return api_error('descripcion demasiado larga (máx 2000 caracteres)')
            e.descripcion = descripcion
        if 'follow_up_fecha' in body:
            if body['follow_up_fecha'] is None:
                e.follow_up_fecha = None
            else:
                try:
                    from datetime import date
                    e.follow_up_fecha = date.fromisoformat(body['follow_up_fecha'])
                except ValueError:
                    return api_error('follow_up_fecha debe ser YYYY-MM-DD')
        if 'follow_up_descripcion' in body:
            e.follow_up_descripcion = str(body['follow_up_descripcion'])[:500]
        if 'follow_up_resuelto' in body:
            e.follow_up_resuelto = bool(body['follow_up_resuelto'])
        if 'plantas_afectadas' in body:
            plantas_uuids = body['plantas_afectadas']
            if not isinstance(plantas_uuids, list):
                return api_error('plantas_afectadas debe ser una lista de uuids')
            plantas_map = {str(p.uuid): p for p in c.plantas.all()}
            plantas = []
            for uuid_str in plantas_uuids:
                planta = plantas_map.get(str(uuid_str))
                if not planta:
                    return api_error(f'planta_uuid desconocido: {uuid_str}')
                plantas.append(planta)
            e.plantas_afectadas.set(plantas)

        e.save()
        return api_ok(_evento(e))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        evento_id_deleted = e.id
        e.delete()
        return api_ok({'deleted': evento_id_deleted})

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def evento_resolver_followup(request, slug, evento_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        e = c.eventos.get(pk=evento_id)
    except Evento.DoesNotExist:
        return api_error('Evento no encontrado', 404)
    if request.method != 'POST':
        return api_error('Method not allowed', 405)
    rl = _write_rate_limit(request)
    if rl:
        return rl
    e.follow_up_resuelto = True
    e.save(update_fields=['follow_up_resuelto'])
    return api_ok(_evento(e))


@csrf_exempt
@require_token
def cultivo_tareas(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        qs = c.tareas.all()
        completada_param = request.GET.get('completada')
        if completada_param == 'false':
            qs = qs.filter(completada=False)
        elif completada_param == 'true':
            qs = qs.filter(completada=True)
        return api_ok([_tarea(t) for t in qs])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        titulo = str(body.get('titulo', '')).strip()
        if not titulo:
            return api_error('titulo es requerido')
        if len(titulo) > 200:
            return api_error('titulo demasiado largo (máx 200 caracteres)')

        prioridad = body.get('prioridad', 'normal')
        if prioridad not in TAREA_PRIORIDADES:
            return api_error(f'prioridad inválida. Opciones: {sorted(TAREA_PRIORIDADES)}')

        categoria = body.get('categoria', 'observacion')
        if categoria not in TAREA_CATEGORIAS:
            return api_error(f'categoria inválida. Opciones: {sorted(TAREA_CATEGORIAS)}')

        fecha_objetivo = None
        if body.get('fecha_objetivo'):
            try:
                from datetime import date
                fecha_objetivo = date.fromisoformat(body['fecha_objetivo'])
            except ValueError:
                return api_error('fecha_objetivo debe ser YYYY-MM-DD')

        t = Tarea.objects.create(
            cultivo=c,
            titulo=titulo,
            descripcion=str(body.get('descripcion', ''))[:1000],
            prioridad=prioridad,
            categoria=categoria,
            fecha_objetivo=fecha_objetivo,
            creado_por=request.api_user,
        )
        return api_ok(_tarea(t), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_tarea_detail(request, slug, tarea_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        t = c.tareas.get(pk=tarea_id)
    except Tarea.DoesNotExist:
        return api_error('Tarea no encontrada', 404)

    if request.method == 'GET':
        return api_ok(_tarea(t))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'titulo' in body:
            titulo = str(body['titulo']).strip()
            if not titulo:
                return api_error('titulo no puede estar vacío')
            if len(titulo) > 200:
                return api_error('titulo demasiado largo (máx 200 caracteres)')
            t.titulo = titulo
        if 'descripcion' in body:
            t.descripcion = str(body['descripcion'])[:1000]
        if 'prioridad' in body:
            if body['prioridad'] not in TAREA_PRIORIDADES:
                return api_error(f'prioridad inválida. Opciones: {sorted(TAREA_PRIORIDADES)}')
            t.prioridad = body['prioridad']
        if 'categoria' in body:
            if body['categoria'] not in TAREA_CATEGORIAS:
                return api_error(f'categoria inválida. Opciones: {sorted(TAREA_CATEGORIAS)}')
            t.categoria = body['categoria']
        if 'fecha_objetivo' in body:
            if body['fecha_objetivo'] is None:
                t.fecha_objetivo = None
            else:
                try:
                    from datetime import date
                    t.fecha_objetivo = date.fromisoformat(body['fecha_objetivo'])
                except ValueError:
                    return api_error('fecha_objetivo debe ser YYYY-MM-DD')
        if 'completada' in body:
            completada = bool(body['completada'])
            t.completada = completada
            t.completada_en = timezone.now() if completada else None

        t.save()
        return api_ok(_tarea(t))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        tarea_id_deleted = t.id
        t.delete()
        return api_ok({'deleted': tarea_id_deleted})

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cultivo_cambios_fotoperiodo(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        return api_ok([_cambio_fotoperiodo(cf) for cf in c.cambios_fotoperiodo.all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        fotoperiodo = str(body.get('fotoperiodo', '')).strip()
        parts = fotoperiodo.split('/')
        if len(parts) != 2:
            return api_error('fotoperiodo debe tener formato N/M (ej: 18/6)')
        try:
            n, m = int(parts[0]), int(parts[1])
        except ValueError:
            return api_error('fotoperiodo debe tener formato N/M con valores numéricos')
        if n + m != 24 or n <= 0 or m <= 0:
            return api_error('N+M del fotoperiodo debe ser igual a 24')

        hora_str = str(body.get('hora_lights_on', '')).strip()
        try:
            from datetime import time
            hora_lights_on = time.fromisoformat(hora_str)
        except (ValueError, TypeError):
            return api_error('hora_lights_on debe ser HH:MM o HH:MM:SS')

        fecha_str = str(body.get('fecha_inicio', '')).strip()
        try:
            from datetime import date
            fecha_inicio = date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            return api_error('fecha_inicio debe ser YYYY-MM-DD')

        try:
            cf = CambioFotoperiodo.objects.create(
                cultivo=c,
                fotoperiodo=fotoperiodo,
                hora_lights_on=hora_lights_on,
                fecha_inicio=fecha_inicio,
                notas=str(body.get('notas', ''))[:500],
            )
        except IntegrityError:
            return api_error('Ya existe un cambio de fotoperiodo para esa fecha en este cultivo')

        return api_ok(_cambio_fotoperiodo(cf), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def cambio_fotoperiodo_detail(request, slug, cf_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        cf = c.cambios_fotoperiodo.get(pk=cf_id)
    except CambioFotoperiodo.DoesNotExist:
        return api_error('Cambio de fotoperiodo no encontrado', 404)

    if request.method == 'GET':
        return api_ok(_cambio_fotoperiodo(cf))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'fotoperiodo' in body:
            fotoperiodo = str(body['fotoperiodo']).strip()
            parts = fotoperiodo.split('/')
            if len(parts) != 2:
                return api_error('fotoperiodo debe tener formato N/M (ej: 18/6)')
            try:
                n, m = int(parts[0]), int(parts[1])
            except ValueError:
                return api_error('fotoperiodo debe tener formato N/M con valores numéricos')
            if n + m != 24 or n <= 0 or m <= 0:
                return api_error('N+M del fotoperiodo debe ser igual a 24')
            cf.fotoperiodo = fotoperiodo
        if 'hora_lights_on' in body:
            try:
                from datetime import time
                cf.hora_lights_on = time.fromisoformat(str(body['hora_lights_on']).strip())
            except (ValueError, TypeError):
                return api_error('hora_lights_on debe ser HH:MM o HH:MM:SS')
        if 'fecha_inicio' in body:
            try:
                from datetime import date
                cf.fecha_inicio = date.fromisoformat(str(body['fecha_inicio']).strip())
            except (ValueError, TypeError):
                return api_error('fecha_inicio debe ser YYYY-MM-DD')
        if 'notas' in body:
            cf.notas = str(body['notas'])[:500]

        try:
            cf.save()
        except IntegrityError:
            return api_error('Ya existe un cambio de fotoperiodo para esa fecha en este cultivo')
        return api_ok(_cambio_fotoperiodo(cf))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        cf_id_deleted = cf.id
        cf.delete()
        return api_ok({'deleted': cf_id_deleted})

    return api_error('Method not allowed', 405)


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
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    plantas_qs = c.plantas.filter(archivado=False).order_by('apodo')

    if request.method == 'GET':
        snapshot = c.canopy_snapshots.first()
        if not snapshot:
            return api_ok(None)
        return api_ok(_canopy_snapshot(snapshot, plantas_qs))

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        scrog_fill_pct = body.get('scrog_fill_pct', 0)
        try:
            scrog_fill_pct = int(scrog_fill_pct)
        except (ValueError, TypeError):
            return api_error('scrog_fill_pct debe ser entero 0-100')
        if not (0 <= scrog_fill_pct <= 100):
            return api_error('scrog_fill_pct fuera de rango (0-100)')

        colas_raw = body.get('colas', [])
        if not isinstance(colas_raw, list):
            return api_error('colas debe ser una lista')

        planta_map = {str(p.uuid): p for p in plantas_qs}
        colas_validated = []
        for item in colas_raw:
            uuid_str = str(item.get('planta_uuid', ''))
            planta = planta_map.get(uuid_str)
            if not planta:
                return api_error(f'planta_uuid desconocido: {uuid_str}')
            try:
                indice = int(item['indice'])
                x = float(item['x'])
                y = float(item['y'])
            except (KeyError, ValueError, TypeError):
                return api_error('Cada cola requiere indice (int), x (float), y (float)')
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return api_error(f'x e y deben estar entre 0.0 y 1.0 (cola planta {uuid_str} indice {indice})')
            colas_validated.append((planta, indice, x, y))

        scrog_cells_raw = body.get('scrog_cells', [])
        if isinstance(scrog_cells_raw, list):
            scrog_cells = [int(i) for i in scrog_cells_raw if 0 <= int(i) < 36]
            if scrog_cells:
                scrog_fill_pct = round(len(scrog_cells) / 36 * 100)
        else:
            scrog_cells = []

        snapshot = CanopySnapshot.objects.create(
            cultivo=c,
            scrog_fill_pct=scrog_fill_pct,
            scrog_cells=scrog_cells,
            notas=str(body.get('notas', ''))[:500],
        )
        ColaPosicion.objects.bulk_create([
            ColaPosicion(snapshot=snapshot, planta=planta, indice=indice, x=x, y=y)
            for planta, indice, x, y in colas_validated
        ])

        return api_ok(_canopy_snapshot(snapshot, plantas_qs), status=201)

    return api_error('Method not allowed', 405)


@require_GET
@require_token
def cultivo_canopy_history(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    snapshots = c.canopy_snapshots.all()
    return api_ok([
        {'id': s.id, 'creado_en': s.creado_en.isoformat(), 'scrog_fill_pct': s.scrog_fill_pct, 'notas': s.notas}
        for s in snapshots
    ])


@require_GET
@require_token
def cultivo_canopy_detail(request, slug, snapshot_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    try:
        snapshot = c.canopy_snapshots.get(pk=snapshot_id)
    except CanopySnapshot.DoesNotExist:
        return api_error('Snapshot no encontrado', 404)

    plantas_qs = c.plantas.filter(archivado=False).order_by('apodo')
    return api_ok(_canopy_snapshot(snapshot, plantas_qs))


@csrf_exempt
@require_token
def cultivo_plantas(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        qs = c.plantas.all()
        if request.GET.get('archivado') == 'false':
            qs = qs.filter(archivado=False)
        return api_ok([_planta_full(p) for p in qs])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        apodo = str(body.get('apodo', '')).strip()
        if not apodo:
            return api_error('apodo es requerido')
        if len(apodo) > 60:
            return api_error('apodo demasiado largo (máx 60 caracteres)')

        posicion_tent = body.get('posicion_tent', 'otro')
        if posicion_tent not in PLANTA_POSICIONES:
            return api_error(f'posicion_tent inválida. Opciones: {sorted(PLANTA_POSICIONES)}')

        estado = body.get('estado', 'activa')
        if estado not in PLANTA_ESTADOS:
            return api_error(f'estado inválido. Opciones: {sorted(PLANTA_ESTADOS)}')

        thc_estimado = None
        if body.get('thc_estimado') is not None:
            try:
                thc_estimado = Decimal(str(body['thc_estimado']))
            except InvalidOperation:
                return api_error('thc_estimado debe ser un número')

        p = Planta.objects.create(
            cultivo=c, apodo=apodo,
            strain=str(body.get('strain', ''))[:120],
            posicion_tent=posicion_tent,
            dias_flora_estimados=body.get('dias_flora_estimados'),
            indica_sativa_ratio=str(body.get('indica_sativa_ratio', ''))[:20],
            thc_estimado=thc_estimado,
            yield_estimado_g=body.get('yield_estimado_g'),
            estado=estado,
            notas_genetica=str(body.get('notas_genetica', ''))[:2000],
            creado_por=request.api_user,
        )
        return api_ok(_planta_full(p), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def planta_detail(request, planta_uuid):
    try:
        p = Planta.objects.select_related('cultivo').get(
            uuid=planta_uuid,
            cultivo__creado_por=request.api_user,
        )
    except Planta.DoesNotExist:
        return api_error('Planta no encontrada', 404)

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
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'apodo' in body:
            apodo = str(body['apodo']).strip()
            if not apodo:
                return api_error('apodo no puede estar vacío')
            p.apodo = apodo[:60]
        if 'strain' in body:
            p.strain = str(body['strain'])[:120]
        if 'posicion_tent' in body:
            if body['posicion_tent'] not in PLANTA_POSICIONES:
                return api_error(f'posicion_tent inválida. Opciones: {sorted(PLANTA_POSICIONES)}')
            p.posicion_tent = body['posicion_tent']
        if 'estado' in body:
            if body['estado'] not in PLANTA_ESTADOS:
                return api_error(f'estado inválido. Opciones: {sorted(PLANTA_ESTADOS)}')
            p.estado = body['estado']
        if 'dias_flora_estimados' in body:
            p.dias_flora_estimados = body['dias_flora_estimados']
        if 'indica_sativa_ratio' in body:
            p.indica_sativa_ratio = str(body['indica_sativa_ratio'])[:20]
        if 'thc_estimado' in body:
            if body['thc_estimado'] is None:
                p.thc_estimado = None
            else:
                try:
                    p.thc_estimado = Decimal(str(body['thc_estimado']))
                except InvalidOperation:
                    return api_error('thc_estimado debe ser un número')
        if 'yield_estimado_g' in body:
            p.yield_estimado_g = body['yield_estimado_g']
        if 'yield_real_g' in body:
            p.yield_real_g = body['yield_real_g']
        if 'notas_genetica' in body:
            p.notas_genetica = str(body['notas_genetica'])[:2000]
        if 'archivado' in body:
            p.archivado = bool(body['archivado'])

        p.save()
        return api_ok(_planta_full(p))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        uuid_deleted = str(p.uuid)
        p.delete()
        return api_ok({'deleted': uuid_deleted})

    return api_error('Method not allowed', 405)


# ── Módulo energético ─────────────────────────────────────────────────────────

def _next_month(d):
    """Primer día del mes siguiente."""
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _tarifa_vigente(hoy):
    """TarifaElectrica con fecha_desde más reciente ≤ hoy, o None."""
    return TarifaElectrica.objects.filter(fecha_desde__lte=hoy).order_by('-fecha_desde').first()


def _ciclo_activo(cultivo, hoy):
    """Fotoperiodo activo según CambioFotoperiodo o estado del cultivo."""
    cf = cultivo.cambios_fotoperiodo.filter(fecha_inicio__lte=hoy).order_by('-fecha_inicio').first()
    if cf:
        return cf.fotoperiodo
    return '12/12' if cultivo.estado == 'floracion' else '18/6'


def _calcular_meses(cultivo_inicio, costos, tarifas, hoy):
    """Lista de dicts por mes desde cultivo_inicio hasta hoy con kWh y costo estimados."""
    import calendar
    meses = []
    mes = cultivo_inicio.replace(day=1)

    while mes <= hoy:
        tarifa_mes = next((t for t in tarifas if t.fecha_desde <= mes), None)

        last_day = calendar.monthrange(mes.year, mes.month)[1]
        mes_fin = mes.replace(day=last_day)

        dia_inicio = max(mes, cultivo_inicio)
        dia_fin = min(mes_fin, hoy)
        dias = (dia_fin - dia_inicio).days + 1

        if dias > 0:
            kwh_mes_val = 0.0
            for ce in costos:
                ce_hasta = ce.fecha_hasta
                if ce.fecha_desde <= dia_fin and (ce_hasta is None or ce_hasta >= dia_inicio):
                    equipo_inicio = max(dia_inicio, ce.fecha_desde)
                    equipo_fin = min(dia_fin, ce_hasta) if ce_hasta else dia_fin
                    dias_equipo = (equipo_fin - equipo_inicio).days + 1
                    kwh_mes_val += float(ce.equipo.watts) / 1000 * float(ce.equipo.horas_dia) * dias_equipo
            kwh_mes_val = round(kwh_mes_val, 2)
            costo_mes_val = round(kwh_mes_val * float(tarifa_mes.precio_kwh), 2) if tarifa_mes else 0.0

            meses.append({
                'mes': mes.strftime('%Y-%m'),
                'dias': dias,
                'kwh_estimado': kwh_mes_val,
                'costo_estimado': costo_mes_val,
                'tarifa': str(tarifa_mes.precio_kwh) if tarifa_mes else None,
            })

        mes = _next_month(mes)

    return meses


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


# ── Endpoints equipos ─────────────────────────────────────────────────────────

EQUIPO_CATEGORIAS = {c[0] for c in Equipo.CATEGORIA_CHOICES}


@csrf_exempt
@require_token
def equipos_list(request):
    if request.method == 'GET':
        equipos = Equipo.objects.all()
        hoy = timezone.localdate()
        tarifa = _tarifa_vigente(hoy)
        precio_kwh = tarifa.precio_kwh if tarifa else None
        return api_ok([_ser_equipo(e, precio_kwh) for e in equipos])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        nombre = str(body.get('nombre', '')).strip()
        if not nombre:
            return api_error('nombre es requerido')

        categoria = body.get('categoria', '')
        if categoria not in EQUIPO_CATEGORIAS:
            return api_error(f'categoria inválida. Opciones: {sorted(EQUIPO_CATEGORIAS)}')

        try:
            watts = Decimal(str(body.get('watts', '')))
            if float(watts) <= 0:
                raise InvalidOperation
        except (InvalidOperation, TypeError):
            return api_error('watts es requerido y debe ser positivo')

        try:
            horas_dia = Decimal(str(body.get('horas_dia', '')))
            if not (0 < float(horas_dia) <= 24):
                raise InvalidOperation
        except (InvalidOperation, TypeError):
            return api_error('horas_dia es requerido y debe estar entre 0 y 24')

        equipo = Equipo.objects.create(
            nombre=nombre[:120], watts=watts, horas_dia=horas_dia, categoria=categoria,
            activo=bool(body.get('activo', True)),
            notas=str(body.get('notas', ''))[:500],
        )
        return api_ok(_ser_equipo(equipo), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def equipo_detail(request, equipo_id):
    try:
        equipo = Equipo.objects.get(pk=equipo_id)
    except Equipo.DoesNotExist:
        return api_error('Equipo no encontrado', 404)

    if request.method == 'GET':
        return api_ok(_ser_equipo(equipo))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'nombre' in body:
            nombre = str(body['nombre']).strip()
            if not nombre:
                return api_error('nombre no puede estar vacío')
            equipo.nombre = nombre[:120]

        if 'categoria' in body:
            if body['categoria'] not in EQUIPO_CATEGORIAS:
                return api_error(f'categoria inválida. Opciones: {sorted(EQUIPO_CATEGORIAS)}')
            equipo.categoria = body['categoria']

        if 'activo' in body:
            equipo.activo = bool(body['activo'])

        if 'horas_dia' in body:
            try:
                horas_dia = Decimal(str(body['horas_dia']))
                if not (0 < float(horas_dia) <= 24):
                    return api_error('horas_dia debe estar entre 0 y 24')
                equipo.horas_dia = horas_dia
            except (InvalidOperation, TypeError):
                return api_error('horas_dia debe ser un número')

        if 'watts' in body:
            try:
                watts = Decimal(str(body['watts']))
                if float(watts) <= 0:
                    return api_error('watts debe ser positivo')
                equipo.watts = watts
            except (InvalidOperation, TypeError):
                return api_error('watts debe ser un número')

        if 'notas' in body:
            equipo.notas = str(body['notas'])[:500]

        equipo.save()
        return api_ok(_ser_equipo(equipo))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        equipo_id_deleted = equipo.id
        equipo.delete()
        return api_ok({'deleted': equipo_id_deleted})

    return api_error('Method not allowed', 405)


# ── Endpoints costos ──────────────────────────────────────────────────────────

@require_GET
@require_token
def cultivo_costos(request, slug):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    hoy = timezone.localdate()
    tarifa = _tarifa_vigente(hoy)
    precio_kwh = tarifa.precio_kwh if tarifa else None

    costos_actuales = list(
        c.costos_energeticos.select_related('equipo', 'tarifa').filter(fecha_hasta__isnull=True)
    )
    todos_costos = list(
        c.costos_energeticos.select_related('equipo').order_by('fecha_desde')
    )
    tarifas = list(TarifaElectrica.objects.filter(fecha_desde__lte=hoy).order_by('-fecha_desde'))

    equipos_data = []
    total_kwh_mes = 0.0
    total_costo_mes = 0.0
    for ce in costos_actuales:
        equipos_data.append(_ser_equipo(ce.equipo, precio_kwh))
        total_kwh_mes += ce.equipo.kwh_mes
        if precio_kwh:
            total_costo_mes += ce.equipo.kwh_mes * float(precio_kwh)

    meses = _calcular_meses(c.fecha_inicio, todos_costos, tarifas, hoy)
    kwh_acumulado = round(sum(m['kwh_estimado'] for m in meses), 2)
    costo_acumulado = round(sum(m['costo_estimado'] for m in meses), 2)

    yield_total = sum(
        p.yield_estimado_g for p in c.plantas.filter(archivado=False)
        if p.yield_estimado_g
    )
    costo_por_gramo = round(costo_acumulado / yield_total, 2) if yield_total > 0 else None

    return api_ok({
        'cultivo': c.slug,
        'tarifa_vigente': _ser_tarifa(tarifa) if tarifa else None,
        'ciclo': _ciclo_activo(c, hoy),
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
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    hoy = timezone.localdate()
    tarifas = list(TarifaElectrica.objects.filter(fecha_desde__lte=hoy).order_by('-fecha_desde'))
    todos_costos = list(
        c.costos_energeticos.select_related('equipo').order_by('fecha_desde')
    )

    meses = _calcular_meses(c.fecha_inicio, todos_costos, tarifas, hoy)
    kwh_total = round(sum(m['kwh_estimado'] for m in meses), 2)
    costo_total = round(sum(m['costo_estimado'] for m in meses), 2)

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
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    lecturas = list(c.lecturas_medidor.all())
    if not lecturas:
        return api_error('No hay lecturas de medidor cargadas para este cultivo', 404)

    hoy = timezone.localdate()
    tarifas = list(TarifaElectrica.objects.filter(fecha_desde__lte=hoy).order_by('-fecha_desde'))
    todos_costos = list(
        c.costos_energeticos.select_related('equipo').order_by('fecha_desde')
    )

    meses = _calcular_meses(c.fecha_inicio, todos_costos, tarifas, hoy)
    kwh_estimado = round(sum(m['kwh_estimado'] for m in meses), 2)
    costo_estimado = round(sum(m['costo_estimado'] for m in meses), 2)

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
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        return api_ok([_ser_lectura(l) for l in c.lecturas_medidor.all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        fecha_str = str(body.get('fecha', '')).strip()
        try:
            from datetime import date
            fecha = date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            return api_error('fecha es requerida (YYYY-MM-DD)')

        try:
            kwh_real = Decimal(str(body.get('kwh_real', '')))
            if float(kwh_real) < 0:
                return api_error('kwh_real debe ser positivo')
        except (InvalidOperation, TypeError):
            return api_error('kwh_real es requerido y debe ser un número')

        l = LecturaMedidor.objects.create(
            cultivo=c,
            fecha=fecha,
            kwh_real=kwh_real,
            notas=str(body.get('notas', ''))[:500],
        )
        return api_ok(_ser_lectura(l), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def lectura_medidor_detail(request, slug, lectura_id):
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        l = c.lecturas_medidor.get(pk=lectura_id)
    except LecturaMedidor.DoesNotExist:
        return api_error('Lectura no encontrada', 404)

    if request.method == 'GET':
        return api_ok(_ser_lectura(l))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'fecha' in body:
            try:
                from datetime import date
                l.fecha = date.fromisoformat(str(body['fecha']).strip())
            except (ValueError, TypeError):
                return api_error('fecha debe ser YYYY-MM-DD')
        if 'kwh_real' in body:
            try:
                kwh_real = Decimal(str(body['kwh_real']))
                if float(kwh_real) < 0:
                    return api_error('kwh_real debe ser positivo')
                l.kwh_real = kwh_real
            except InvalidOperation:
                return api_error('kwh_real debe ser un número')
        if 'notas' in body:
            l.notas = str(body['notas'])[:500]

        l.save()
        return api_ok(_ser_lectura(l))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        lectura_id_deleted = l.id
        l.delete()
        return api_ok({'deleted': lectura_id_deleted})

    return api_error('Method not allowed', 405)


# ── Endpoints tarifas ─────────────────────────────────────────────────────────

@csrf_exempt
@require_token
def tarifas_list(request):
    if request.method == 'GET':
        return api_ok([_ser_tarifa(t) for t in TarifaElectrica.objects.all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        try:
            from datetime import date
            fecha_desde = date.fromisoformat(str(body.get('fecha_desde', '')).strip())
        except (ValueError, TypeError):
            return api_error('fecha_desde es requerida (YYYY-MM-DD)')

        try:
            precio_kwh = Decimal(str(body.get('precio_kwh', '')))
            if float(precio_kwh) <= 0:
                raise InvalidOperation
        except (InvalidOperation, TypeError):
            return api_error('precio_kwh es requerido y debe ser positivo')

        tarifa = TarifaElectrica.objects.create(
            fecha_desde=fecha_desde, precio_kwh=precio_kwh,
            distribuidora=str(body.get('distribuidora', 'Edesur'))[:100],
            notas=str(body.get('notas', ''))[:500],
        )
        return api_ok(_ser_tarifa(tarifa), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def tarifa_detail(request, tarifa_id):
    try:
        tarifa = TarifaElectrica.objects.get(pk=tarifa_id)
    except TarifaElectrica.DoesNotExist:
        return api_error('Tarifa no encontrada', 404)

    if request.method == 'GET':
        return api_ok(_ser_tarifa(tarifa))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'fecha_desde' in body:
            try:
                from datetime import date
                tarifa.fecha_desde = date.fromisoformat(str(body['fecha_desde']).strip())
            except (ValueError, TypeError):
                return api_error('fecha_desde debe ser YYYY-MM-DD')
        if 'precio_kwh' in body:
            try:
                precio_kwh = Decimal(str(body['precio_kwh']))
                if float(precio_kwh) <= 0:
                    return api_error('precio_kwh debe ser positivo')
                tarifa.precio_kwh = precio_kwh
            except InvalidOperation:
                return api_error('precio_kwh debe ser un número')
        if 'distribuidora' in body:
            tarifa.distribuidora = str(body['distribuidora'])[:100]
        if 'notas' in body:
            tarifa.notas = str(body['notas'])[:500]

        tarifa.save()
        return api_ok(_ser_tarifa(tarifa))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        try:
            tarifa_id_deleted = tarifa.id
            tarifa.delete()
        except IntegrityError:
            return api_error('No se puede eliminar: hay costos energéticos que referencian esta tarifa', 409)
        return api_ok({'deleted': tarifa_id_deleted})

    return api_error('Method not allowed', 405)


# ── Endpoints costos energéticos por cultivo (asignación de equipos) ──────────

def _ser_costo(ce):
    return {
        'id': ce.id,
        'equipo': _ser_equipo(ce.equipo),
        'tarifa_id': ce.tarifa_id,
        'fecha_desde': ce.fecha_desde.isoformat(),
        'fecha_hasta': ce.fecha_hasta.isoformat() if ce.fecha_hasta else None,
    }


@csrf_exempt
@require_token
def cultivo_costos_equipos(request, slug):
    """GET lista / POST asigna un Equipo a este cultivo con vigencia desde una fecha."""
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err

    if request.method == 'GET':
        return api_ok([_ser_costo(ce) for ce in c.costos_energeticos.select_related('equipo').all()])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        try:
            equipo = Equipo.objects.get(pk=int(body.get('equipo_id', '')))
        except (Equipo.DoesNotExist, ValueError, TypeError):
            return api_error('equipo_id es requerido y debe existir')

        try:
            from datetime import date
            fecha_desde = date.fromisoformat(str(body.get('fecha_desde', '')).strip())
        except (ValueError, TypeError):
            return api_error('fecha_desde es requerida (YYYY-MM-DD)')

        hoy = timezone.localdate()
        tarifa = _tarifa_vigente(hoy)
        if not tarifa:
            return api_error('No hay tarifa eléctrica cargada — creá una en /api/v1/tarifas/ primero')

        ce = CostoEnergetico.objects.create(
            cultivo=c, equipo=equipo, tarifa=tarifa, fecha_desde=fecha_desde,
        )
        return api_ok(_ser_costo(ce), status=201)

    return api_error('Method not allowed', 405)


@csrf_exempt
@require_token
def costo_detail(request, slug, costo_id):
    """PATCH acepta fecha_hasta para dar de baja un equipo del cultivo (fin de vigencia)."""
    c, err = _get_cultivo(slug, request.api_user)
    if err:
        return err
    try:
        ce = c.costos_energeticos.select_related('equipo').get(pk=costo_id)
    except CostoEnergetico.DoesNotExist:
        return api_error('Costo energético no encontrado', 404)

    if request.method == 'GET':
        return api_ok(_ser_costo(ce))

    if request.method == 'PATCH':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        if 'fecha_hasta' in body:
            if body['fecha_hasta'] is None:
                ce.fecha_hasta = None
            else:
                try:
                    from datetime import date
                    ce.fecha_hasta = date.fromisoformat(str(body['fecha_hasta']).strip())
                except ValueError:
                    return api_error('fecha_hasta debe ser YYYY-MM-DD')

        ce.save()
        return api_ok(_ser_costo(ce))

    if request.method == 'DELETE':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        costo_id_deleted = ce.id
        ce.delete()
        return api_ok({'deleted': costo_id_deleted})

    return api_error('Method not allowed', 405)


# ── Endpoints de referencia (solo lectura) ────────────────────────────────────

@require_GET
@require_token
def nutrientes_list(request):
    return api_ok([
        {
            'id': n.id, 'nombre': n.nombre, 'marca': n.marca, 'npk': n.npk,
            'etapa_recomendada': n.etapa_recomendada,
            'etapa_recomendada_display': n.get_etapa_recomendada_display(),
            'dosis_recomendada_min': str(n.dosis_recomendada_min) if n.dosis_recomendada_min is not None else None,
            'dosis_recomendada_max': str(n.dosis_recomendada_max) if n.dosis_recomendada_max is not None else None,
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
            'ec_min': str(p.ec_min) if p.ec_min is not None else None,
            'ec_max': str(p.ec_max) if p.ec_max is not None else None,
            'vpd_min': str(p.vpd_min), 'vpd_max': str(p.vpd_max),
            'horas_luz': p.horas_luz,
            'distancia_luz_min': p.distancia_luz_min,
            'distancia_luz_max': p.distancia_luz_max,
        }
        for p in ParametroIdeal.objects.all()
    ])
