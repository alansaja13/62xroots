import uuid
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import APIToken, Cultivo, Planta


# ── Helpers ──────────────────────────────────────────────────────────────────

def api_ok(data):
    return JsonResponse({'ok': True, 'data': data})


def api_error(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


def require_token(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Bearer '):
            return api_error('Authentication required', 401)
        token_str = auth[7:].strip()
        try:
            token_uuid = uuid.UUID(token_str)
            token = APIToken.objects.select_related('user').get(token=token_uuid)
        except (ValueError, APIToken.DoesNotExist):
            return api_error('Invalid token', 401)
        request.api_user = token.user
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Serializers ───────────────────────────────────────────────────────────────

def _cultivo_base(c):
    return {
        'id': c.id,
        'nombre': c.nombre,
        'estado': c.estado,
        'fecha_inicio': c.fecha_inicio.isoformat(),
        'dias_desde_inicio': c.dias_desde_inicio,
        'lampara_watts_reales': c.lampara_watts_reales,
        'sustrato': c.sustrato,
        'carpa_dimensiones': c.carpa_dimensiones,
    }


def _planta(p):
    return {'id': p.id, 'apodo': p.apodo, 'strain': p.strain, 'estado': p.estado}


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


def _medicion(m):
    return {
        'id': m.id,
        'timestamp': m.timestamp.isoformat(),
        'temperatura_c': str(m.temperatura_c),
        'humedad_relativa': str(m.humedad_relativa),
        'vpd': m.vpd,
        'vpd_estado': m.vpd_estado,
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


# ── Views ─────────────────────────────────────────────────────────────────────

@require_GET
@require_token
def cultivos_list(request):
    cultivos = Cultivo.objects.filter(archivado=False)
    return api_ok([_cultivo_base(c) for c in cultivos])


@require_GET
@require_token
def cultivo_detail(request, pk):
    try:
        c = Cultivo.objects.get(pk=pk)
    except Cultivo.DoesNotExist:
        return api_error('Cultivo no encontrado', 404)

    data = _cultivo_base(c)
    data['notas'] = c.notas
    data['plantas'] = [_planta(p) for p in c.plantas.filter(archivado=False)]
    data['ultimos_riegos'] = [_riego(r, include_nutrientes=False) for r in c.riegos.all()[:5]]
    data['ultimas_mediciones'] = [_medicion(m) for m in c.mediciones.all()[:5]]
    data['ultimos_eventos'] = [
        _evento(e) for e in c.eventos.prefetch_related('plantas_afectadas').all()[:10]
    ]
    data['tareas_pendientes'] = [_tarea(t) for t in c.tareas.filter(completada=False)]
    return api_ok(data)


@require_GET
@require_token
def cultivo_riegos(request, pk):
    try:
        c = Cultivo.objects.get(pk=pk)
    except Cultivo.DoesNotExist:
        return api_error('Cultivo no encontrado', 404)

    riegos = c.riegos.prefetch_related('nutrientes_aplicados__nutriente').all()
    return api_ok([_riego(r) for r in riegos])


@require_GET
@require_token
def cultivo_mediciones(request, pk):
    try:
        c = Cultivo.objects.get(pk=pk)
    except Cultivo.DoesNotExist:
        return api_error('Cultivo no encontrado', 404)

    return api_ok([_medicion(m) for m in c.mediciones.all()])


@require_GET
@require_token
def cultivo_eventos(request, pk):
    try:
        c = Cultivo.objects.get(pk=pk)
    except Cultivo.DoesNotExist:
        return api_error('Cultivo no encontrado', 404)

    eventos = c.eventos.prefetch_related('plantas_afectadas').all()
    return api_ok([_evento(e) for e in eventos])


@require_GET
@require_token
def cultivo_tareas(request, pk):
    try:
        c = Cultivo.objects.get(pk=pk)
    except Cultivo.DoesNotExist:
        return api_error('Cultivo no encontrado', 404)

    qs = c.tareas.all()
    completada_param = request.GET.get('completada')
    if completada_param == 'false':
        qs = qs.filter(completada=False)
    elif completada_param == 'true':
        qs = qs.filter(completada=True)

    return api_ok([_tarea(t) for t in qs])


@require_GET
@require_token
def planta_detail(request, pk):
    try:
        p = Planta.objects.select_related('cultivo').get(pk=pk)
    except Planta.DoesNotExist:
        return api_error('Planta no encontrada', 404)

    data = {
        'id': p.id,
        'apodo': p.apodo,
        'strain': p.strain,
        'estado': p.estado,
        'posicion_tent': p.posicion_tent,
        'dias_flora_estimados': p.dias_flora_estimados,
        'indica_sativa_ratio': p.indica_sativa_ratio,
        'thc_estimado': str(p.thc_estimado) if p.thc_estimado is not None else None,
        'yield_estimado_g': p.yield_estimado_g,
        'notas_genetica': p.notas_genetica,
        'cultivo': {'id': p.cultivo.id, 'nombre': p.cultivo.nombre},
        'mediciones': [_medicion_planta(m) for m in p.mediciones.all()],
    }
    return api_ok(data)
