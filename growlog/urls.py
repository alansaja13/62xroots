from django.urls import path
from . import views
from . import api_views

app_name = "growlog"

urlpatterns = [
    # ── API v1 ────────────────────────────────────────────────────────────────
    path("api/v1/cultivos/", api_views.cultivos_list),
    path("api/v1/cultivos/<slug:slug>/", api_views.cultivo_detail),

    # Plantas
    path("api/v1/cultivos/<slug:slug>/plantas/", api_views.cultivo_plantas),
    path("api/v1/plantas/<uuid:planta_uuid>/", api_views.planta_detail),
    path("api/v1/plantas/<uuid:planta_uuid>/mediciones/", api_views.planta_mediciones),
    path("api/v1/plantas/<uuid:planta_uuid>/mediciones/<int:medicion_id>/", api_views.medicion_planta_detail),

    # Riego + detalle por planta + nutrientes aplicados
    path("api/v1/cultivos/<slug:slug>/riegos/", api_views.cultivo_riegos),
    path("api/v1/cultivos/<slug:slug>/riegos/<int:riego_id>/", api_views.cultivo_riego_detail),
    path("api/v1/cultivos/<slug:slug>/riegos/<int:riego_id>/plantas/", api_views.cultivo_riego_plantas),
    path("api/v1/cultivos/<slug:slug>/riegos/<int:riego_id>/plantas/<int:rp_id>/", api_views.riego_planta_detail),
    path("api/v1/cultivos/<slug:slug>/riegos/<int:riego_id>/nutrientes/", api_views.cultivo_riego_nutrientes),
    path("api/v1/cultivos/<slug:slug>/riegos/<int:riego_id>/nutrientes/<int:na_id>/", api_views.riego_nutriente_detail),

    # Mediciones de ambiente y EC/pH
    path("api/v1/cultivos/<slug:slug>/mediciones/", api_views.cultivo_mediciones),
    path("api/v1/cultivos/<slug:slug>/mediciones/<int:medicion_id>/", api_views.cultivo_medicion_detail),
    path("api/v1/cultivos/<slug:slug>/mediciones-ec/", api_views.cultivo_mediciones_ec),
    path("api/v1/cultivos/<slug:slug>/mediciones-ec/<int:medicion_id>/", api_views.medicion_ec_detail),

    # Eventos
    path("api/v1/cultivos/<slug:slug>/eventos/", api_views.cultivo_eventos),
    path("api/v1/cultivos/<slug:slug>/eventos/<int:evento_id>/", api_views.cultivo_evento_detail),
    path("api/v1/cultivos/<slug:slug>/eventos/<int:evento_id>/resolver-followup/", api_views.evento_resolver_followup),

    # Tareas
    path("api/v1/cultivos/<slug:slug>/tareas/", api_views.cultivo_tareas),
    path("api/v1/cultivos/<slug:slug>/tareas/<int:tarea_id>/", api_views.cultivo_tarea_detail),

    # Fotoperiodo
    path("api/v1/cultivos/<slug:slug>/cambios-fotoperiodo/", api_views.cultivo_cambios_fotoperiodo),
    path("api/v1/cultivos/<slug:slug>/cambios-fotoperiodo/<int:cf_id>/", api_views.cambio_fotoperiodo_detail),

    # Canopy
    path("api/v1/cultivos/<slug:slug>/canopy/", api_views.cultivo_canopy),
    path("api/v1/cultivos/<slug:slug>/canopy/history/", api_views.cultivo_canopy_history),
    path("api/v1/cultivos/<slug:slug>/canopy/<int:snapshot_id>/", api_views.cultivo_canopy_detail),

    # Referencia (solo lectura)
    path("api/v1/nutrientes/", api_views.nutrientes_list),
    path("api/v1/parametros-ideales/", api_views.parametros_ideales_list),

    # Módulo energético
    path("api/v1/equipos/", api_views.equipos_list),
    path("api/v1/equipos/<int:equipo_id>/", api_views.equipo_detail),
    path("api/v1/tarifas/", api_views.tarifas_list),
    path("api/v1/tarifas/<int:tarifa_id>/", api_views.tarifa_detail),
    path("api/v1/cultivos/<slug:slug>/costos/", api_views.cultivo_costos),
    path("api/v1/cultivos/<slug:slug>/costos/historico/", api_views.cultivo_costos_historico),
    path("api/v1/cultivos/<slug:slug>/costos/comparacion/", api_views.cultivo_costos_comparacion),
    path("api/v1/cultivos/<slug:slug>/costos/equipos/", api_views.cultivo_costos_equipos),
    path("api/v1/cultivos/<slug:slug>/costos/equipos/<int:costo_id>/", api_views.costo_detail),
    path("api/v1/cultivos/<slug:slug>/lecturas-medidor/", api_views.cultivo_lecturas_medidor),
    path("api/v1/cultivos/<slug:slug>/lecturas-medidor/<int:lectura_id>/", api_views.lectura_medidor_detail),

    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),

    # Push notifications
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),

    # Invitados
    path("invitados/", views.invitados_panel, name="invitados_panel"),
    path("invitados/crear/", views.invitado_crear, name="invitado_crear"),
    path("invitados/<int:pk>/eliminar/", views.invitado_eliminar, name="invitado_eliminar"),

    # Cultivo
    path("cultivo/nuevo/", views.nuevo_cultivo, name="nuevo_cultivo"),
    path("cultivo/<slug:slug>/", views.cultivo_detail, name="cultivo_detail"),
    path("cultivo/<slug:slug>/editar/", views.cultivo_editar, name="cultivo_editar"),
    path("cultivo/<slug:slug>/marcar-flora/", views.cultivo_marcar_flora, name="cultivo_marcar_flora"),
    path("cultivo/<slug:slug>/finalizar/", views.cultivo_finalizar, name="cultivo_finalizar"),
    path("cultivo/<slug:slug>/tendencias/", views.cultivo_tendencias, name="cultivo_tendencias"),
    path("cultivo/<slug:slug>/tendencias.json", views.cultivo_tendencias_json, name="cultivo_tendencias_json"),
    path("cultivo/<slug:slug>/quick/", views.quick_entry, name="quick"),
    path("cultivo/<slug:slug>/quick/evento/", views.quick_evento, name="quick_evento"),
    path("cultivo/<slug:slug>/quick/tarea/", views.quick_tarea, name="quick_tarea"),
    path("cultivo/<slug:slug>/quick/ec/", views.quick_medicion_ec, name="quick_ec"),
    path("cultivo/<slug:slug>/timeline/", views.timeline, name="timeline"),
    path("cultivo/<slug:slug>/reporte/", views.cultivo_reporte, name="reporte"),
    path("cultivo/<slug:slug>/canopy/", views.canopy_view, name="canopy"),
    path("cultivo/<slug:slug>/energia/", views.cultivo_energia, name="energia"),
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

    # CambioEtapaPlanta
    path("planta/<int:pk>/etapa/", views.planta_etapa_list, name="planta_etapa_list"),
    path("etapa-planta/<int:pk>/editar/", views.cambio_etapa_planta_editar, name="cambio_etapa_planta_editar"),
    path("etapa-planta/<int:pk>/eliminar/", views.cambio_etapa_planta_eliminar, name="cambio_etapa_planta_eliminar"),
]
