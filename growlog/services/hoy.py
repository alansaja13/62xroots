"""Lectura del inicio: datos observados y pendientes, sin inferir salud del cultivo."""
from django.db.models import Case, Count, DateField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Evento, MedicionAmbiente, Tarea
from ..permissions import cultivos_visibles


def resumen_hoy(usuario, *, ahora=None):
    ahora = ahora or timezone.now()
    hoy = timezone.localdate(ahora)
    ultima = MedicionAmbiente.objects.filter(cultivo_id=OuterRef("pk")).order_by("-timestamp", "-pk")
    cultivos = list(cultivos_visibles(usuario).annotate(
        plantas_count=Count("plantas", filter=Q(plantas__estado="activa", plantas__archivado=False), distinct=True),
        ultima_id=Subquery(ultima.values("pk")[:1]),
    ).order_by("-fecha_inicio", "-pk"))
    editables = set(cultivos_visibles(usuario, editar=True).values_list("pk", flat=True))
    mediciones = MedicionAmbiente.objects.in_bulk(c.ultima_id for c in cultivos if c.ultima_id)
    activos, finalizados, archivados = [], [], []
    for cultivo in cultivos:
        medicion = mediciones.get(cultivo.ultima_id)
        fecha = timezone.localdate(medicion.timestamp) if medicion else None
        frescura = "sin_datos" if not fecha else "futura" if medicion.timestamp > ahora else "hoy" if fecha == hoy else "anterior"
        item = {"cultivo": cultivo, "ultima_medicion": medicion,
                "plantas_count": cultivo.plantas_count, "puede_editar": cultivo.pk in editables,
                "frescura": frescura}
        (archivados if cultivo.archivado else finalizados if cultivo.estado == "finalizado" else activos).append(item)

    ids = [item["cultivo"].pk for item in activos]
    tareas = Tarea.objects.filter(cultivo_id__in=ids, completada=False)
    conteos = tareas.aggregate(total=Count("pk"), sin_fecha=Count("pk", filter=Q(fecha_objetivo__isnull=True)))
    # El orden de prioridad es de producto, no el orden alfabético de sus valores.
    prioridades = {"urgente": 0, "normal": 1, "baja": 2}
    atencion = []
    relevantes = tareas.filter(Q(fecha_objetivo__lte=hoy) | Q(prioridad="urgente"))
    seguimientos = Evento.objects.filter(cultivo_id__in=ids, follow_up_resuelto=False, follow_up_fecha__lte=hoy)
    total = relevantes.count() + seguimientos.count()
    primeras = relevantes.annotate(
        orden_vencida=Case(When(fecha_objetivo__lt=hoy, then=Value(0)), default=Value(1)),
        orden_fecha=Coalesce("fecha_objetivo", Value(hoy), output_field=DateField()),
        orden_prioridad=Case(When(prioridad="urgente", then=Value(0)),
                             When(prioridad="baja", then=Value(2)), default=Value(1)),
    ).order_by("orden_vencida", "orden_fecha", "orden_prioridad", "pk").select_related("cultivo")[:12]
    for tarea in primeras:
        atencion.append({"tipo": "Tarea", "titulo": tarea.titulo, "cultivo": tarea.cultivo,
                         "fecha": tarea.fecha_objetivo, "urgente": tarea.prioridad == "urgente",
                         "prioridad": prioridades.get(tarea.prioridad, 1), "pk": tarea.pk})
    for evento in seguimientos.order_by("follow_up_fecha", "pk").select_related("cultivo")[:12]:
        atencion.append({"tipo": "Seguimiento", "titulo": evento.follow_up_descripcion or evento.descripcion,
                         "cultivo": evento.cultivo, "fecha": evento.follow_up_fecha,
                         "urgente": False, "prioridad": 1, "pk": evento.pk})
    for item in atencion:
        item["vencido"] = bool(item["fecha"] and item["fecha"] < hoy)
    atencion.sort(key=lambda item: (not item["vencido"], item["fecha"] or hoy,
                                   item["prioridad"], item["tipo"], item["pk"]))
    return {"hoy": hoy, "activos": activos, "finalizados": finalizados, "archivados": archivados,
            "atencion": atencion[:12], "atencion_total": total,
            "atencion_restante": max(0, total - 12), "tareas_total": conteos["total"],
            "tareas_sin_fecha": conteos["sin_fecha"], "puede_registrar": bool(editables),
            "sin_medicion_hoy": sum(item["frescura"] != "hoy" for item in activos)}
