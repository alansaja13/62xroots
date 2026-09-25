"""Mapa de canopy."""
import json
import math

from django.contrib.auth.decorators import login_required
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
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    scrog_fill_pct = body.get('scrog_fill_pct', 0)
    try:
        scrog_fill_pct = max(0, min(100, int(scrog_fill_pct)))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'scrog_fill_pct inválido'}, status=400)

    colas_raw = body.get('colas', [])
    if not isinstance(colas_raw, list):
        return JsonResponse({'ok': False, 'error': 'colas debe ser lista'}, status=400)

    plantas_qs = cultivo.plantas.filter(archivado=False)
    planta_map = {str(p.uuid): p for p in plantas_qs}

    colas_validated = []
    for item in colas_raw:
        uuid_str = str(item.get('planta_uuid', ''))
        planta = planta_map.get(uuid_str)
        if not planta:
            return JsonResponse({'ok': False, 'error': f'UUID desconocido: {uuid_str}'}, status=400)
        try:
            indice = int(item['indice'])
            x = float(item['x'])
            y = float(item['y'])
        except (KeyError, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'Cola requiere indice, x, y'}, status=400)
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return JsonResponse({'ok': False, 'error': 'x e y deben estar en [0,1]'}, status=400)
        colas_validated.append((planta, indice, x, y))

    scrog_cells_raw = body.get('scrog_cells', [])
    if isinstance(scrog_cells_raw, list):
        scrog_cells = [int(i) for i in scrog_cells_raw if 0 <= int(i) < 36]
        if scrog_cells:
            scrog_fill_pct = round(len(scrog_cells) / 36 * 100)
    else:
        scrog_cells = []

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
