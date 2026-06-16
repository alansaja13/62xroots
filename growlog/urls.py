from django.urls import path
from . import views
from . import api_views

app_name = "growlog"

urlpatterns = [
    # ── API v1 ────────────────────────────────────────────────────────────────
    path("api/v1/cultivos/", api_views.cultivos_list),
    path("api/v1/cultivos/<slug:slug>/", api_views.cultivo_detail),
    path("api/v1/cultivos/<slug:slug>/riegos/", api_views.cultivo_riegos),
    path("api/v1/cultivos/<slug:slug>/riegos/<int:riego_id>/", api_views.cultivo_riego_detail),
    path("api/v1/cultivos/<slug:slug>/mediciones/", api_views.cultivo_mediciones),
    path("api/v1/cultivos/<slug:slug>/eventos/", api_views.cultivo_eventos),
    path("api/v1/cultivos/<slug:slug>/tareas/", api_views.cultivo_tareas),
    path("api/v1/cultivos/<slug:slug>/cambios-fotoperiodo/", api_views.cultivo_cambios_fotoperiodo),
    path("api/v1/plantas/<uuid:planta_uuid>/", api_views.planta_detail),
    path("api/v1/cultivos/<slug:slug>/canopy/", api_views.cultivo_canopy),
    path("api/v1/cultivos/<slug:slug>/canopy/history/", api_views.cultivo_canopy_history),
    path("api/v1/cultivos/<slug:slug>/canopy/<int:snapshot_id>/", api_views.cultivo_canopy_detail),

    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),

    # Invitados
    path("invitados/", views.invitados_panel, name="invitados_panel"),
    path("invitados/crear/", views.invitado_crear, name="invitado_crear"),
    path("invitados/<int:pk>/eliminar/", views.invitado_eliminar, name="invitado_eliminar"),

    # Cultivo
    path("cultivo/nuevo/", views.nuevo_cultivo, name="nuevo_cultivo"),
    path("cultivo/<slug:slug>/", views.cultivo_detail, name="cultivo_detail"),
    path("cultivo/<slug:slug>/editar/", views.cultivo_editar, name="cultivo_editar"),
    path("cultivo/<slug:slug>/marcar-flora/", views.cultivo_marcar_flora, name="cultivo_marcar_flora"),
    path("cultivo/<slug:slug>/quick/", views.quick_entry, name="quick"),
    path("cultivo/<slug:slug>/quick/evento/", views.quick_evento, name="quick_evento"),
    path("cultivo/<slug:slug>/quick/tarea/", views.quick_tarea, name="quick_tarea"),
    path("cultivo/<slug:slug>/quick/ec/", views.quick_medicion_ec, name="quick_ec"),
    path("cultivo/<slug:slug>/timeline/", views.timeline, name="timeline"),
    path("cultivo/<slug:slug>/reporte/", views.cultivo_reporte, name="reporte"),
    path("cultivo/<slug:slug>/canopy/", views.canopy_view, name="canopy"),
    path("cultivo/<slug:slug>/canopy/guardar/", views.canopy_guardar, name="canopy_guardar"),
    path("cultivo/<slug:slug>/canopy/snapshot/<int:snapshot_id>/json/", views.canopy_snapshot_json, name="canopy_snapshot_json"),

    # Planta
    path("cultivo/<slug:slug>/planta/nueva/", views.planta_crear, name="planta_crear"),
    path("planta/<int:pk>/", views.planta_detail, name="planta_detail"),
    path("planta/<int:pk>/editar/", views.planta_editar, name="planta_editar"),
    path("planta/<int:pk>/eliminar/", views.planta_eliminar, name="planta_eliminar"),

    # Tarea
    path("cultivo/<slug:slug>/tareas/", views.tareas_list, name="tareas_list"),
    path("cultivo/<slug:slug>/tarea/nueva/", views.tarea_crear, name="tarea_crear"),
    path("tarea/<int:pk>/editar/", views.tarea_editar, name="tarea_editar"),
    path("tarea/<int:pk>/eliminar/", views.tarea_eliminar, name="tarea_eliminar"),
    path("tarea/<int:pk>/completar/", views.tarea_completar, name="tarea_completar"),
    path("tarea/<int:pk>/descompletar/", views.tarea_descompletar, name="tarea_descompletar"),

    # Evento
    path("cultivo/<slug:slug>/evento/nuevo/", views.evento_crear, name="evento_crear"),
    path("evento/<int:pk>/editar/", views.evento_editar, name="evento_editar"),
    path("evento/<int:pk>/eliminar/", views.evento_eliminar, name="evento_eliminar"),
    path("evento/<int:pk>/resolver-followup/", views.evento_resolver_followup, name="evento_resolver_followup"),

    # Riego
    path("cultivo/<slug:slug>/riego/nuevo/", views.riego_crear, name="riego_crear"),
    path("riego/<int:pk>/editar/", views.riego_editar, name="riego_editar"),
    path("riego/<int:pk>/eliminar/", views.riego_eliminar, name="riego_eliminar"),

    # NutrienteAplicado
    path("riego/<int:riego_pk>/nutriente/agregar/", views.nutriente_aplicado_crear, name="nutriente_aplicado_crear"),
    path("nutriente-aplicado/<int:pk>/eliminar/", views.nutriente_aplicado_eliminar, name="nutriente_aplicado_eliminar"),

    # MedicionPlanta
    path("planta/<int:planta_pk>/medicion/nueva/", views.medicion_planta_crear, name="medicion_planta_crear"),
    path("medicion-planta/<int:pk>/editar/", views.medicion_planta_editar, name="medicion_planta_editar"),
    path("medicion-planta/<int:pk>/eliminar/", views.medicion_planta_eliminar, name="medicion_planta_eliminar"),

    # MedicionEC
    path("cultivo/<slug:slug>/medicion-ec/nueva/", views.medicion_ec_crear, name="medicion_ec_crear"),
    path("medicion-ec/<int:pk>/editar/", views.medicion_ec_editar, name="medicion_ec_editar"),
    path("medicion-ec/<int:pk>/eliminar/", views.medicion_ec_eliminar, name="medicion_ec_eliminar"),

    # CambioFotoperiodo
    path("cultivo/<slug:slug>/fotoperiodo/", views.fotoperiodo_list, name="fotoperiodo_list"),
    path("fotoperiodo/<int:pk>/editar/", views.cambio_fotoperiodo_editar, name="cambio_fotoperiodo_editar"),
    path("fotoperiodo/<int:pk>/eliminar/", views.cambio_fotoperiodo_eliminar, name="cambio_fotoperiodo_eliminar"),
]
