from django.conf import settings
from django.urls import reverse
from django.db.models import OuterRef, Subquery
from django.utils.functional import SimpleLazyObject

from .models import CultivoMiembro
from .permissions import cultivos_visibles

# Pestaña del menú del cultivo que queda marcada en cada pantalla.
SECCIONES_CULTIVO = {
    "cultivo_detail": "resumen", "planta_detail": "resumen", "planta_etapa_list": "resumen",
    "timeline": "bitacora",
    "tareas_list": "tareas",
    "cultivo_tendencias": "tendencias",
    "canopy": "canopy",
    "energia": "energia",
    "reporte": "reporte",
    "cultivo_ajustes": "ajustes", "cultivo_etapa": "ajustes", "fotoperiodo_list": "ajustes",
}

# Pestañas del cultivo: (sección, etiqueta, ícono, url name). Las "extra" van
# al menú "Más" en el celular para que no haya que adivinar un scroll lateral.
PESTANAS_CULTIVO = [
    ("resumen", "Resumen", "flower1", "cultivo_detail", False),
    ("bitacora", "Bitácora", "journal-text", "timeline", False),
    ("tareas", "Tareas", "check2-square", "tareas_list", False),
    ("tendencias", "Tendencias", "graph-up", "cultivo_tendencias", True),
    ("canopy", "Canopy", "grid-3x3-gap", "canopy", True),
    ("energia", "Energía", "lightning-charge", "energia", True),
    ("reporte", "Reporte", "clipboard-data", "reporte", True),
    ("ajustes", "Ajustes", "gear", "cultivo_ajustes", True),
]


def pestanas_cultivo(cultivo, *, puede_editar, seccion):
    return [
        {"seccion": clave, "etiqueta": etiqueta, "icono": icono, "extra": extra, "activa": clave == seccion,
         "url": reverse(f"growlog:{url_name}", args=[cultivo.slug])}
        for clave, etiqueta, icono, url_name, extra in PESTANAS_CULTIVO
        if clave != "ajustes" or puede_editar
    ]


def push_settings(request):
    cultivo = getattr(request, "cultivo_actual", None)
    return {
        "vapid_public_key": settings.VAPID_PUBLIC_KEY,
        "can_edit_cultivo": getattr(request, "puede_editar_cultivo", False),
        "can_manage_cultivo": bool(cultivo and cultivo.propietario_id == request.user.pk),
    }


def cultivos_del_menu(usuario):
    """Cultivos visibles agrupados para el selector: propios activos,
    compartidos activos (con el rol) e historial (finalizados o archivados)."""
    rol = CultivoMiembro.objects.filter(cultivo=OuterRef("pk"), usuario=usuario).values("rol")[:1]
    cultivos = (cultivos_visibles(usuario).select_related("propietario")
                .annotate(rol_miembro=Subquery(rol)).order_by("-fecha_inicio", "-pk"))
    grupos = {"activos": [], "compartidos": [], "historial": []}
    for cultivo in cultivos:
        if cultivo.archivado or cultivo.estado == "finalizado":
            grupos["historial"].append(cultivo)
        elif cultivo.propietario_id == usuario.pk:
            grupos["activos"].append(cultivo)
        else:
            grupos["compartidos"].append(cultivo)
    grupos["total"] = sum(len(v) for v in grupos.values())
    return grupos


def navegacion(request):
    if not request.user.is_authenticated:
        return {}
    match = request.resolver_match
    cultivo = getattr(request, "cultivo_actual", None)
    seccion = SECCIONES_CULTIVO.get(match.url_name if match else None)
    pestanas = []
    if cultivo is not None:
        pestanas = pestanas_cultivo(cultivo, seccion=seccion,
                                    puede_editar=getattr(request, "puede_editar_cultivo", False))
    return {
        "cultivo_nav": cultivo,
        "seccion_cultivo": seccion,
        "pestanas_cultivo": pestanas,
        "pestana_extra_activa": next((p for p in pestanas if p["extra"] and p["activa"]), None),
        # Perezoso: solo consulta si la plantilla dibuja el selector.
        "nav_cultivos": SimpleLazyObject(lambda: cultivos_del_menu(request.user)),
    }
