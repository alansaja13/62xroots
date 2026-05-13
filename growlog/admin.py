from django.contrib import admin
from .models import (
    CambioFotoperiodo, Cultivo, Planta, MedicionAmbiente, Nutriente, Riego,
    NutrienteAplicado, Evento, MedicionPlanta, Tarea, ParametroIdeal,
)


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
    inlines = [PlantaInline, MedicionAmbienteInline, RiegoInline, TareaInline]
    readonly_fields = ["dias_desde_inicio", "creado_en"]
    fieldsets = [
        (None, {"fields": ["nombre", "estado", "fecha_inicio", "fecha_fin", "archivado"]}),
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

