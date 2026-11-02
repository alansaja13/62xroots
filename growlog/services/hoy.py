"""Lectura del inicio: datos observados y pendientes, sin inferir salud del cultivo."""
from django.db.models import Case, Count, DateField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from datetime import timedelta

from ..models import Evento, MedicionAmbiente, ParametroIdeal, Riego, Tarea
from ..permissions import cultivos_visibles
from ..utils import etapa_efectiva_cultivo
from .vpd import estado_de

# Una lectura de ambiente más vieja que esto se muestra como dato viejo.
DATO_VIEJO = timedelta(hours=6)
# Las alertas de VPD solo se levantan con lecturas recientes.
ALERTA_VPD_HASTA = timedelta(hours=24)
# Nombre corto de la etapa para el pill de Hoy ("Veg · día 28").
ETAPA_CORTA = {"plantula": "Plántula", "veg_temprano": "Veg", "veg_tardio": "Veg",
               "flora_temprana": "Flora", "flora_tardia": "Flora", "secado": "Secado", "curado": "Curado"}


def resumen_hoy(usuario, *, ahora=None):
    ahora = ahora or timezone.now()
    hoy = timezone.localdate(ahora)
    ultima = MedicionAmbiente.objects.filter(cultivo_id=OuterRef("pk")).order_by("-timestamp", "-pk")
    ultimo_riego = Riego.objects.filter(cultivo_id=OuterRef("pk")).order_by("-timestamp", "-pk")
    cultivos = list(cultivos_visibles(usuario).annotate(
        plantas_count=Count("plantas", filter=Q(plantas__estado="activa", plantas__archivado=False), distinct=True),
        ultima_id=Subquery(ultima.values("pk")[:1]),
        ultimo_riego_ts=Subquery(ultimo_riego.values("timestamp")[:1]),
    ).select_related("propietario").prefetch_related("cambios_etapa").order_by("-fecha_inicio", "-pk"))
    # Los rangos ideales se leen una vez para todos (estado_de los busca por cultivo).
    parametros = {p.etapa: p for p in ParametroIdeal.objects.all()}
    for cultivo in cultivos:
        cultivo.__dict__["_parametro_por_etapa"] = parametros
    editables = set(cultivos_visibles(usuario, editar=True).values_list("pk", flat=True))
    mediciones = MedicionAmbiente.objects.in_bulk(c.ultima_id for c in cultivos if c.ultima_id)
    activos, finalizados, archivados = [], [], []
    for cultivo in cultivos:
        medicion = mediciones.get(cultivo.ultima_id)
        fecha = timezone.localdate(medicion.timestamp) if medicion else None
        frescura = "sin_datos" if not fecha else "futura" if medicion.timestamp > ahora else "hoy" if fecha == hoy else "anterior"
        etapa = etapa_efectiva_cultivo(cultivo, hoy)
        flora = cultivo.fecha_inicio_flora and cultivo.fecha_inicio_flora <= hoy and etapa not in ("plantula", "veg_temprano", "veg_tardio")
        item = {"cultivo": cultivo, "ultima_medicion": medicion,
                "plantas_count": cultivo.plantas_count, "puede_editar": cultivo.pk in editables,
                "frescura": frescura, "es_propio": cultivo.propietario_id == usuario.pk,
                "etapa": etapa, "etapa_nombre": ETAPA_CORTA.get(etapa),
                "en_flora": bool(flora),
                "dia": (hoy - cultivo.fecha_inicio_flora).days if flora else cultivo.dias_desde_inicio,
                "vpd_estado": estado_de(cultivo, medicion) if medicion else None,
                "dato_viejo": bool(medicion and ahora - medicion.timestamp > DATO_VIEJO),
                "dias_sin_riego": (hoy - timezone.localdate(cultivo.ultimo_riego_ts)).days if cultivo.ultimo_riego_ts else None}
        (archivados if cultivo.archivado else finalizados if cultivo.estado == "finalizado" else activos).append(item)

    # Aire fuera de rango en una lectura reciente: va primero en "Para revisar".
    alertas = [{"tipo": "Aire", "cultivo": item["cultivo"], "medicion": item["ultima_medicion"],
                "estado": item["vpd_estado"], "puede_editar": item["puede_editar"]}
               for item in activos
               if item["vpd_estado"] in ("alto", "bajo") and ahora - item["ultima_medicion"].timestamp <= ALERTA_VPD_HASTA]

    ids = [item["cultivo"].pk for item in activos]
    tareas = Tarea.objects.filter(cultivo_id__in=ids, completada=False)
    conteos = tareas.aggregate(total=Count("pk"), sin_fecha=Count("pk", filter=Q(fecha_objetivo__isnull=True)))
    # El orden de prioridad es de producto, no el orden alfabético de sus valores.
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
        atencion.append(item_tarea(tarea, puede_editar=tarea.cultivo_id in editables, hoy=hoy))
    for evento in seguimientos.order_by("follow_up_fecha", "pk").select_related("cultivo")[:12]:
        atencion.append({"tipo": "Seguimiento", "titulo": evento.follow_up_descripcion or evento.descripcion,
                         "cultivo": evento.cultivo, "fecha": evento.follow_up_fecha,
                         "urgente": False, "prioridad": 1, "pk": evento.pk, "puede_editar": evento.cultivo_id in editables})
    for item in atencion:
        item["vencido"] = bool(item["fecha"] and item["fecha"] < hoy)
    atencion.sort(key=lambda item: (not item["vencido"], item["fecha"] or hoy,
                                   item["prioridad"], item["tipo"], item["pk"]))
    return {"hoy": hoy, "activos": activos,
            "propios": [item for item in activos if item["es_propio"]],
            "compartidos": [item for item in activos if not item["es_propio"]], "finalizados": finalizados, "archivados": archivados, "historial_total": len(finalizados) + len(archivados),
            "atencion": atencion[:12], "atencion_total": total + len(alertas), "alertas": alertas,
            "atencion_restante": max(0, total - 12), "tareas_total": conteos["total"],
            "tareas_sin_fecha": conteos["sin_fecha"], "puede_registrar": bool(editables),
            "sin_medicion_hoy": sum(item["frescura"] != "hoy" for item in activos)}


def item_tarea(tarea, *, puede_editar, hoy=None):
    """Una tarea como fila de "Para revisar" (también la usa completar/deshacer desde Hoy)."""
    hoy = hoy or timezone.localdate()
    return {"tipo": "Tarea", "titulo": tarea.titulo, "cultivo": tarea.cultivo,
            "fecha": tarea.fecha_objetivo, "urgente": tarea.prioridad == "urgente",
            "prioridad": {"urgente": 0, "normal": 1, "baja": 2}.get(tarea.prioridad, 1), "pk": tarea.pk,
            "puede_editar": puede_editar, "vencido": bool(tarea.fecha_objetivo and tarea.fecha_objetivo < hoy),
            "categoria": tarea.get_categoria_display()}
