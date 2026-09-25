"""Mapa de canopy."""
import json
import math

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import CanopySnapshot, ColaPosicion, Cultivo, POSICION_TENT_COORDS
from ..permissions import objeto_del_cultivo


_PLANT_COLORS = ["#b1d160", "#d4923a", "#d96a3d", "#b384d8", "#79a4d4", "#f3e9d1"]


def _default_colas(cx, cy, n=2, radius=50):
    return [
        {
            "indice": i,
            "x": round(cx + radius * math.cos(2 * math.pi * i / n - math.pi / 2), 1),
            "y": round(cy + radius * math.sin(2 * math.pi * i / n - math.pi / 2), 1),
        }
        for i in range(n)
    ]


@login_required
def canopy_view(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    plantas = list(cultivo.plantas.filter(archivado=False).order_by('apodo'))
    snapshots_qs = cultivo.canopy_snapshots.all()
    latest = snapshots_qs.first()

    colas_by_planta = {}
    if latest:
        for cp in latest.colas.select_related('planta').all():
            colas_by_planta.setdefault(cp.planta_id, []).append({
                "indice": cp.indice,
                "x": round(cp.x * 400, 1),
                "y": round(cp.y * 400, 1),
            })

    plantas_data = []
    for i, p in enumerate(plantas):
        cx_n, cy_n = POSICION_TENT_COORDS.get(p.posicion_tent, (0.50, 0.50))
        cx = round(cx_n * 400, 1)
        cy = round(cy_n * 400, 1)
        colas = colas_by_planta.get(p.id) or _default_colas(cx, cy, 2)
        plantas_data.append({
            "uuid": str(p.uuid),
            "apodo": p.apodo,
            "color": _PLANT_COLORS[i % len(_PLANT_COLORS)],
            "cx": cx,
            "cy": cy,
            "colas": colas,
        })

    snapshots_data = [
        {
            "id": s.id,
            "label": s.creado_en.strftime("%d/%m/%Y %H:%M"),
            "scrog_fill_pct": s.scrog_fill_pct,
        }
        for s in snapshots_qs
    ]

    init_data = {
        "editable": request.puede_editar_cultivo,
        "slug": cultivo.slug,
        "watts": cultivo.lampara_watts_reales or 314,
        "plantas": plantas_data,
        "scrog_fill_pct": latest.scrog_fill_pct if latest else 0,
        "scrog_cells": list(latest.scrog_cells) if latest and latest.scrog_cells else [],
        "notas": latest.notas if latest else "",
        "currentSnapshotId": latest.id if latest else None,
        "snapshots": snapshots_data,
    }

    return render(request, "growlog/canopy.html", {
        "cultivo": cultivo,
        "init_data": init_data,
    })


@login_required
@require_POST
def canopy_guardar(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    def error(mensaje):
        return JsonResponse({'ok': False, 'error': mensaje}, status=400)

    try:
        body = json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error('JSON inválido')
    if not isinstance(body, dict):
        return error('El cuerpo debe ser un objeto JSON')

    try:
        scrog_fill_pct = max(0, min(100, int(body.get('scrog_fill_pct', 0))))
    except (ValueError, TypeError, OverflowError):
        return error('scrog_fill_pct inválido')

    colas_raw = body.get('colas', [])
    if not isinstance(colas_raw, list):
        return error('colas debe ser lista')

    planta_map = {str(p.uuid): p for p in cultivo.plantas.filter(archivado=False)}
    colas_validated, vistas = [], set()
    for item in colas_raw:
        if not isinstance(item, dict):
            return error('Cada cola debe ser un objeto')
        uuid_str = str(item.get('planta_uuid', ''))
        planta = planta_map.get(uuid_str)
        if not planta:
            return error(f'UUID desconocido: {uuid_str}')
        try:
            indice = int(item['indice'])
            x = float(item['x'])
            y = float(item['y'])
        except (KeyError, ValueError, TypeError, OverflowError):
            return error('Cola requiere indice, x, y')
        if not 0 <= indice <= 32767:
            return error('indice fuera de rango')
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return error('x e y deben estar en [0,1]')
        if (planta.pk, indice) in vistas:
            return error(f'Cola repetida: {planta.apodo} #{indice}')
        vistas.add((planta.pk, indice))
        colas_validated.append((planta, indice, x, y))

    scrog_cells_raw = body.get('scrog_cells', [])
    if not isinstance(scrog_cells_raw, list):
        return error('scrog_cells debe ser lista')
    try:
        scrog_cells = sorted({int(i) for i in scrog_cells_raw if not isinstance(i, bool)})
    except (ValueError, TypeError, OverflowError):
        return error('scrog_cells debe contener números de celda')
    scrog_cells = [i for i in scrog_cells if 0 <= i < 36]
    if scrog_cells:
        scrog_fill_pct = round(len(scrog_cells) / 36 * 100)

    with transaction.atomic():
        snapshot = CanopySnapshot.objects.create(
            cultivo=cultivo,
            scrog_fill_pct=scrog_fill_pct,
            scrog_cells=scrog_cells,
            notas=str(body.get('notas', ''))[:500],
        )
        ColaPosicion.objects.bulk_create([
            ColaPosicion(snapshot=snapshot, planta=planta, indice=indice, x=x, y=y)
            for planta, indice, x, y in colas_validated
        ])

    return JsonResponse({
        'ok': True,
        'data': {
            'id': snapshot.id,
            'creado_en': snapshot.creado_en.isoformat(),
            'scrog_fill_pct': snapshot.scrog_fill_pct,
            'scrog_cells': snapshot.scrog_cells,
        }
    }, status=201)


@login_required
def canopy_snapshot_json(request, slug, snapshot_id):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    try:
        snapshot = cultivo.canopy_snapshots.get(pk=snapshot_id)
    except CanopySnapshot.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'No encontrado'}, status=404)

    plantas_qs = cultivo.plantas.filter(archivado=False).order_by('apodo')
    colas_by_planta = {}
    for cp in snapshot.colas.select_related('planta').all():
        colas_by_planta.setdefault(cp.planta_id, []).append({
            "indice": cp.indice,
            "x": cp.x,
            "y": cp.y,
        })

    plantas_data = []
    for p in plantas_qs:
        plantas_data.append({
            "uuid": str(p.uuid),
            "apodo": p.apodo,
            "colas": colas_by_planta.get(p.id, []),
        })

    return JsonResponse({
        'ok': True,
        'data': {
            'id': snapshot.id,
            'creado_en': snapshot.creado_en.isoformat(),
            'scrog_fill_pct': snapshot.scrog_fill_pct,
            'scrog_cells': snapshot.scrog_cells,
            'notas': snapshot.notas,
            'plantas': plantas_data,
        }
    })


# ---------------------------------------------------------------------------
