"""Resumen de cada planta para la lista y la ficha: altura actual, ritmo, curva y fotos."""
from django.utils import timezone

DIAS_MEDICION_VIEJA = 5


def curva(puntos, ancho, alto, margen=3):
    """Puntos (día, valor) a coordenadas SVG dentro de ancho × alto."""
    if not puntos:
        return []
    d0, d1 = puntos[0][0], puntos[-1][0]
    v0, v1 = min(v for _, v in puntos), max(v for _, v in puntos)
    span_d, span_v = (d1 - d0) or 1, (v1 - v0) or 1
    return [(round(margen + (d - d0) / span_d * (ancho - 2 * margen), 1),
             round(alto - margen - (v - v0) / span_v * (alto - 2 * margen), 1)) for d, v in puntos]


def resumen_planta(planta, mediciones, hoy=None):
    """`mediciones` de la planta en orden de fecha (de la más vieja a la más nueva)."""
    hoy = hoy or timezone.localdate()
    con_altura = [m for m in mediciones if m.altura_cm is not None]
    ultima = mediciones[-1] if mediciones else None
    altura = float(con_altura[-1].altura_cm) if con_altura else None
    ritmo = None
    if len(con_altura) >= 2:
        a, b = con_altura[-2], con_altura[-1]
        dias = (b.fecha - a.fecha).days
        if dias > 0:
            ritmo = round((float(b.altura_cm) - float(a.altura_cm)) / dias, 1)
    inicio = con_altura[0].fecha if con_altura else None
    puntos = [((m.fecha - inicio).days, float(m.altura_cm)) for m in con_altura]
    sparkline = " ".join(f"{x},{y}" for x, y in curva(puntos, 140, 34)) if len(puntos) >= 2 else ""
    con_foto = [m for m in mediciones if m.foto]
    dias_sin_medir = (hoy - ultima.fecha).days if ultima else None
    return {
        "planta": planta, "altura": altura, "ritmo": ritmo, "ultima": ultima,
        "dias_sin_medir": dias_sin_medir,
        "medicion_vieja": dias_sin_medir is None or dias_sin_medir > DIAS_MEDICION_VIEJA,
        "sparkline": sparkline, "portada": con_foto[-1] if con_foto else None,
        "fotos": list(reversed(con_foto)), "con_altura": con_altura,
    }
