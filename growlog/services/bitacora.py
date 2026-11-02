"""Bitácora del cultivo (Núcleo): todos los registros en orden, por páginas.

Junta ambiente, riegos, eventos, pH/EC, cambios de etapa y de fotoperíodo y
mediciones de planta. Cada fuente se pide ordenada y solo hasta la página que
se muestra, así que el costo no depende del largo del historial.
"""
from datetime import datetime, time

from django.utils import timezone

from ..models import MedicionPlanta

POR_PAGINA = 50

# Filtro → (etiqueta, tipos de registro que incluye)
FILTROS = {
    "medicion": ("Ambiente", ("medicion",)),
    "riego": ("Riego", ("riego",)),
    "evento": ("Evento", ("evento",)),
    "medicion_ec": ("pH/EC", ("medicion_ec",)),
    "ciclo": ("Ciclo", ("etapa", "fotoperiodo")),
    "planta": ("Plantas", ("planta",)),
}


def _a_fecha_hora(fecha):
    """Los registros con solo fecha van al principio de su día."""
    return timezone.make_aware(datetime.combine(fecha, time.min))


def _fuentes(cultivo):
    """Tipo → (queryset ordenado del más nuevo al más viejo, función que da su momento)."""
    return {
        "medicion": (cultivo.mediciones.select_related("creado_por").order_by("-timestamp", "-pk"),
                     lambda o: o.timestamp),
        "riego": (cultivo.riegos.select_related("creado_por")
                  .prefetch_related("detalle_plantas__planta", "nutrientes_aplicados__nutriente")
                  .order_by("-timestamp", "-pk"), lambda o: o.timestamp),
        "evento": (cultivo.eventos.select_related("creado_por").prefetch_related("plantas_afectadas")
                   .order_by("-timestamp", "-pk"), lambda o: o.timestamp),
        "medicion_ec": (cultivo.mediciones_ec.select_related("creado_por").order_by("-timestamp", "-pk"),
                        lambda o: o.timestamp),
        "etapa": (cultivo.cambios_etapa.order_by("-fecha_inicio", "-pk"), lambda o: _a_fecha_hora(o.fecha_inicio)),
        "fotoperiodo": (cultivo.cambios_fotoperiodo.order_by("-fecha_inicio", "-pk"),
                        lambda o: _a_fecha_hora(o.fecha_inicio)),
        "planta": (MedicionPlanta.objects.filter(planta__cultivo=cultivo).select_related("planta")
                   .order_by("-fecha", "-pk"), lambda o: _a_fecha_hora(o.fecha)),
    }


def bitacora(cultivo, filtro="", desde=0, por_pagina=POR_PAGINA, dia_anterior=None):
    if filtro not in FILTROS:
        filtro = ""
    fuentes = _fuentes(cultivo)
    tipos = FILTROS[filtro][1] if filtro else tuple(fuentes)
    hasta = desde + por_pagina

    items = []
    for tipo in tipos:
        qs, momento = fuentes[tipo]
        for obj in qs[:hasta + 1]:
            ts = momento(obj)
            items.append({"tipo": tipo, "ts": ts, "obj": obj, "dia": timezone.localdate(ts)})
    items.sort(key=lambda i: (i["ts"], i["obj"].pk), reverse=True)
    pagina = items[desde:hasta]

    # Separador de día: solo cuando cambia, también entre una página y la siguiente.
    anterior = dia_anterior
    for item in pagina:
        item["nuevo_dia"] = item["dia"] != anterior
        anterior = item["dia"]

    conteos = {clave: sum(fuentes[t][0].count() for t in incluidos) for clave, (_, incluidos) in FILTROS.items()}
    return {
        "registros": pagina,
        "filtro": filtro,
        "filtros": [{"clave": k, "etiqueta": v[0], "cuenta": conteos[k]} for k, v in FILTROS.items()],
        "total": sum(conteos.values()),
        "hay_mas": len(items) > hasta,
        "siguiente": hasta,
        "ultimo_dia": pagina[-1]["dia"] if pagina else dia_anterior,
    }
