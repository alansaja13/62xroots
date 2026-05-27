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
    Cultivo, Evento, MedicionAmbiente, Nutriente, NutrienteAplicado,
    Planta, POSICION_TENT_COORDS, Riego, Tarea,
)

EVENTO_TIPOS = {c[0] for c in Evento.TIPO_CHOICES}
TAREA_PRIORIDADES = {c[0] for c in Tarea.PRIORIDAD_CHOICES}
TAREA_CATEGORIAS = {c[0] for c in Tarea.CATEGORIA_CHOICES}

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


def _riego(r, include_nutrientes=True):
    d = {
        'id': r.id,
        'timestamp': r.timestamp.isoformat(),
        'volumen_total_ml': r.volumen_total_ml,
        'volumen_por_planta_ml': r.volumen_por_planta_ml,
        'ph_agua': str(r.ph_agua) if r.ph_agua is not None else None,
        'ec_solucion': str(r.ec_solucion) if r.ec_solucion is not None else None,
        'runoff_observado': r.runoff_observado,
        'notas': r.notas,
    }
    if include_nutrientes:
        d['nutrientes_aplicados'] = [
            {'nutriente': str(na.nutriente), 'dosis_g_por_litro': str(na.dosis_g_por_litro)}
            for na in r.nutrientes_aplicados.select_related('nutriente').all()
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
    data['ultimos_riegos'] = [_riego(r, include_nutrientes=False) for r in c.riegos.all()[:5]]
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
        riegos = c.riegos.prefetch_related('nutrientes_aplicados__nutriente').all()
        return api_ok([_riego(r) for r in riegos])

    if request.method == 'POST':
        rl = _write_rate_limit(request)
        if rl:
            return rl
        body, err = _parse_json_body(request)
        if err:
            return err

        try:
            volumen_total_ml = int(body.get('volumen_total_ml', ''))
            if volumen_total_ml <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return api_error('volumen_total_ml es requerido y debe ser entero positivo')

        volumen_por_planta_ml = None
        if body.get('volumen_por_planta_ml') is not None:
            try:
                volumen_por_planta_ml = int(body['volumen_por_planta_ml'])
                if volumen_por_planta_ml <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return api_error('volumen_por_planta_ml debe ser entero positivo')

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

        runoff_observado = bool(body.get('runoff_observado', False))
        notas = str(body.get('notas', ''))[:500]

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
            volumen_total_ml=volumen_total_ml,
            volumen_por_planta_ml=volumen_por_planta_ml,
            ph_agua=ph_agua,
            ec_solucion=ec_solucion,
            runoff_observado=runoff_observado,
            notas=notas,
            creado_por=request.api_user,
        )
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
        riego = c.riegos.prefetch_related('nutrientes_aplicados__nutriente').get(pk=riego_id)
    except Riego.DoesNotExist:
        return api_error('Riego no encontrado', 404)

    if request.method == 'GET':
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

        e = Evento.objects.create(
            cultivo=c,
            tipo=tipo,
            descripcion=descripcion,
            follow_up_fecha=follow_up_fecha,
            follow_up_descripcion=str(body.get('follow_up_descripcion', ''))[:500],
            creado_por=request.api_user,
        )
        return api_ok(_evento(e), status=201)

    return api_error('Method not allowed', 405)


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


@require_GET
@require_token
def planta_detail(request, planta_uuid):
    try:
        p = Planta.objects.select_related('cultivo').get(
            uuid=planta_uuid,
            cultivo__creado_por=request.api_user,
        )
    except Planta.DoesNotExist:
        return api_error('Planta no encontrada', 404)

    data = {
        'id': p.id,
        'uuid': str(p.uuid),
        'apodo': p.apodo,
        'strain': p.strain,
        'estado': p.estado,
        'posicion_tent': p.posicion_tent,
        'dias_flora_estimados': p.dias_flora_estimados,
        'indica_sativa_ratio': p.indica_sativa_ratio,
        'thc_estimado': str(p.thc_estimado) if p.thc_estimado is not None else None,
        'yield_estimado_g': p.yield_estimado_g,
        'notas_genetica': p.notas_genetica,
        'cultivo': {'id': p.cultivo.id, 'slug': p.cultivo.slug, 'nombre': p.cultivo.nombre},
        'mediciones': [_medicion_planta(m) for m in p.mediciones.all()],
    }
    return api_ok(data)
