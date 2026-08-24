from django.contrib import admin
from .models import (
    CambioFotoperiodo, CostoEnergetico, Cultivo, Equipo, LecturaMedidor,
    MedicionAmbiente, MedicionEC, MedicionPlanta, Nutriente, NutrienteAplicado,
    Evento, Planta, PushSubscription, Tarea, TarifaElectrica, ParametroIdeal, Riego,
)


class CostoEnergeticoInline(admin.TabularInline):
    model = CostoEnergetico
    extra = 1
    fields = ['equipo', 'tarifa', 'fecha_desde', 'fecha_hasta']


class LecturaMedidorInline(admin.TabularInline):
    model = LecturaMedidor
    extra = 0
    fields = ['fecha', 'kwh_real', 'notas']
    ordering = ['-fecha']


class PlantaInline(admin.TabularInline):
    model = Planta
    extra = 1
    fields = ["apodo", "strain", "posicion_tent", "estado", "archivado"]


class MedicionAmbienteInline(admin.TabularInline):
    model = MedicionAmbiente
    extra = 0
    fields = ["timestamp", "temperatura_c", "humedad_relativa", "notas"]
    ordering = ["-timestamp"]
    max_num = 10


class RiegoInline(admin.TabularInline):
    model = Riego
    extra = 0
    fields = ["timestamp", "volumen_total_ml", "ph_agua", "ec_solucion"]
    ordering = ["-timestamp"]
    max_num = 10


class TareaInline(admin.TabularInline):
    model = Tarea
    extra = 1
    fields = ["titulo", "categoria", "prioridad", "fecha_objetivo", "completada"]


@admin.register(Cultivo)
class CultivoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "estado", "fecha_inicio", "dias_desde_inicio", "archivado"]
    list_filter = ["estado", "archivado"]
    search_fields = ["nombre", "sustrato"]
    inlines = [PlantaInline, MedicionAmbienteInline, RiegoInline, TareaInline, CostoEnergeticoInline, LecturaMedidorInline]
    readonly_fields = ["dias_desde_inicio", "creado_en"]
    fieldsets = [
        (None, {"fields": ["nombre", "estado", "fecha_inicio", "fecha_inicio_flora", "fecha_fin", "archivado"]}),
        ("Setup", {"fields": ["carpa_dimensiones", "sustrato", "lampara_modelo", "lampara_watts_reales"]}),
        ("Info", {"fields": ["notas", "dias_desde_inicio", "creado_en"]}),
    ]


@admin.register(Planta)
class PlantaAdmin(admin.ModelAdmin):
    list_display = ["apodo", "cultivo", "strain", "posicion_tent", "estado"]
    list_filter = ["estado", "cultivo", "archivado"]
    search_fields = ["apodo", "strain"]


class NutrienteAplicadoInline(admin.TabularInline):
    model = NutrienteAplicado
    extra = 1


@admin.register(Riego)
class RiegoAdmin(admin.ModelAdmin):
    list_display = ["cultivo", "timestamp", "volumen_total_ml", "ph_agua", "ec_solucion", "runoff_observado"]
    list_filter = ["cultivo", "buscar_runoff", "runoff_observado"]
    inlines = [NutrienteAplicadoInline]


@admin.register(CambioFotoperiodo)
class CambioFotoperiodoAdmin(admin.ModelAdmin):
    list_display = ("cultivo", "fotoperiodo", "hora_lights_on", "fecha_inicio")
    list_filter = ("cultivo", "fotoperiodo")


@admin.register(MedicionAmbiente)
class MedicionAmbienteAdmin(admin.ModelAdmin):
    list_display = ["cultivo", "timestamp", "temperatura_c", "humedad_relativa", "vpd_display", "luz_estado"]
    list_filter = ["cultivo", "luz_estado"]
    readonly_fields = ["vpd_display", "luz_estado"]

    @admin.display(description="VPD (kPa)")
    def vpd_display(self, obj):
        return obj.vpd


@admin.register(Nutriente)
class NutrienteAdmin(admin.ModelAdmin):
    list_display = ["nombre", "marca", "npk", "etapa_recomendada", "dosis_recomendada_min", "dosis_recomendada_max"]
    list_filter = ["etapa_recomendada", "marca"]


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["cultivo", "tipo", "timestamp", "follow_up_resuelto"]
    list_filter = ["tipo", "cultivo", "follow_up_resuelto"]
    filter_horizontal = ["plantas_afectadas"]


@admin.register(MedicionPlanta)
class MedicionPlantaAdmin(admin.ModelAdmin):
    list_display = ["planta", "fecha", "altura_cm", "nudos_count", "aspecto_general"]
    list_filter = ["aspecto_general", "planta__cultivo"]


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ["titulo", "cultivo", "categoria", "prioridad", "fecha_objetivo", "completada"]
    list_filter = ["completada", "prioridad", "categoria", "cultivo"]
    list_editable = ["completada"]


@admin.register(ParametroIdeal)
class ParametroIdealAdmin(admin.ModelAdmin):
    list_display = ["etapa", "temp_min", "temp_max", "hr_min", "hr_max", "vpd_min", "vpd_max"]


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "creado_en", "endpoint"]
    list_filter = ["user"]


@admin.register(MedicionEC)
class MedicionECAdmin(admin.ModelAdmin):
    list_display = ["cultivo", "timestamp", "tipo", "ph", "ec", "temp_agua"]
    list_filter = ["cultivo", "tipo"]


# ── Módulo energético ─────────────────────────────────────────────────────────

@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "watts", "horas_dia", "kwh_mes_display", "activo"]
    list_filter = ["categoria", "activo"]
    list_editable = ["activo", "horas_dia"]
    search_fields = ["nombre"]

    @admin.display(description="kWh/mes")
    def kwh_mes_display(self, obj):
        return obj.kwh_mes


@admin.register(TarifaElectrica)
class TarifaElectricaAdmin(admin.ModelAdmin):
    list_display = ["distribuidora", "precio_kwh", "fecha_desde", "notas"]
    ordering = ["-fecha_desde"]


@admin.register(CostoEnergetico)
class CostoEnergeticoAdmin(admin.ModelAdmin):
    list_display = ["cultivo", "equipo", "tarifa", "fecha_desde", "fecha_hasta"]
    list_filter = ["cultivo", "equipo", "tarifa"]
    raw_id_fields = ["cultivo", "equipo", "tarifa"]


@admin.register(LecturaMedidor)
class LecturaMedidorAdmin(admin.ModelAdmin):
    list_display = ["cultivo", "fecha", "kwh_real", "notas"]
    list_filter = ["cultivo"]
    ordering = ["-fecha"]

