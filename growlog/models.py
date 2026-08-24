import math
import uuid
from django.core.cache import cache
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify


class Cultivo(models.Model):
    ESTADO_CHOICES = [
        ("plantula", "Plántula"),
        ("vegetativo", "Vegetativo"),
        ("floracion", "Floración"),
        ("secado", "Secado"),
        ("curado", "Curado"),
        ("finalizado", "Finalizado"),
    ]

    nombre = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    carpa_dimensiones = models.CharField(max_length=80, blank=True)
    sustrato = models.CharField(max_length=120, blank=True)
    lampara_watts_reales = models.PositiveSmallIntegerField(null=True, blank=True)
    lampara_modelo = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="vegetativo")
    dias_veg_estimados = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Días de vegetativo estimados",
        help_text="Días totales esperados en etapa vegetativa (desde inicio).",
    )
    dias_flora_estimados = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Días de floración estimados",
        help_text="Días esperados en etapa de floración.",
    )
    fecha_inicio_flora = models.DateField(
        null=True, blank=True,
        verbose_name="Fecha de inicio de floración",
        help_text="Fecha en que se marcó el cambio a floración (flip a ≤12h de luz).",
    )
    notas = models.TextField(blank=True)
    archivado = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cultivos_creados')

    class Meta:
        ordering = ["-fecha_inicio"]
        verbose_name = "Cultivo"
        verbose_name_plural = "Cultivos"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre)
            slug, n = base, 2
            while Cultivo.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def dias_desde_inicio(self):
        """Día 1 = fecha_inicio (mismo criterio 1-indexado que dia_flora)."""
        return (timezone.localdate() - self.fecha_inicio).days + 1

    @property
    def dia_flora(self):
        """Día 1 = fecha_inicio_flora. None si todavía no se marcó el flip."""
        if not self.fecha_inicio_flora:
            return None
        hoy = timezone.localdate()
        if self.fecha_inicio_flora > hoy:
            return None
        return (hoy - self.fecha_inicio_flora).days + 1


class Planta(models.Model):
    POSICION_CHOICES = [
        ("centro", "Centro"),
        ("arriba_izq", "Arriba izquierda"),
        ("arriba_der", "Arriba derecha"),
        ("abajo_izq", "Abajo izquierda"),
        ("abajo_der", "Abajo derecha"),
        ("otro", "Otro"),
    ]
    ESTADO_CHOICES = [
        ("activa", "Activa"),
        ("descartada", "Descartada"),
        ("cosechada", "Cosechada"),
    ]

    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="plantas")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    apodo = models.CharField(max_length=60)
    strain = models.CharField(max_length=120, blank=True)
    posicion_tent = models.CharField(max_length=20, choices=POSICION_CHOICES, default="otro")
    dias_flora_estimados = models.PositiveSmallIntegerField(null=True, blank=True)
    indica_sativa_ratio = models.CharField(max_length=20, blank=True, help_text="Ej: 70/30")
    thc_estimado = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    yield_estimado_g = models.PositiveSmallIntegerField(null=True, blank=True)
    yield_real_g = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Yield real (g)",
        help_text="Peso seco final cosechado de esta planta.",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activa")
    notas_genetica = models.TextField(blank=True)
    archivado = models.BooleanField(default=False)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='plantas_creadas')

    class Meta:
        ordering = ["apodo"]
        verbose_name = "Planta"
        verbose_name_plural = "Plantas"

    def __str__(self):
        return f"{self.apodo} ({self.strain or 'sin strain'})"


class CambioFotoperiodo(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="cambios_fotoperiodo")
    fotoperiodo = models.CharField(
        max_length=5,
        verbose_name="Fotoperiodo",
        help_text="Formato N/M donde N+M=24. Ej: 18/6, 12/12",
    )
    hora_lights_on = models.TimeField(
        verbose_name="Hora de encendido",
        help_text="Hora local (Argentina) en que se enciende la luz",
    )
    fecha_inicio = models.DateField(
        verbose_name="Fecha de inicio",
        help_text="Fecha desde la cual rige este fotoperiodo",
    )
    notas = models.TextField(blank=True, verbose_name="Notas")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_inicio"]
        unique_together = [("cultivo", "fecha_inicio")]
        verbose_name = "Cambio de fotoperiodo"
        verbose_name_plural = "Cambios de fotoperiodo"

    def __str__(self):
        return f"{self.cultivo} — {self.fotoperiodo} desde {self.fecha_inicio:%d/%m/%Y}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fotoperiodo:
            parts = self.fotoperiodo.split("/")
            if len(parts) != 2:
                raise ValidationError({"fotoperiodo": "Formato inválido. Use N/M donde N+M=24 (ej: 18/6)."})
            try:
                n, m = int(parts[0]), int(parts[1])
            except ValueError:
                raise ValidationError({"fotoperiodo": "Formato inválido. Use N/M con números enteros."})
            if n + m != 24 or n <= 0 or m <= 0:
                raise ValidationError({"fotoperiodo": "N+M debe sumar exactamente 24."})


class MedicionAmbiente(models.Model):
    LUZ_ESTADO_CHOICES = [("on", "Luz prendida"), ("off", "Luz apagada")]

    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="mediciones")
    timestamp = models.DateTimeField(default=timezone.now)
    temperatura_c = models.DecimalField(max_digits=5, decimal_places=2)
    humedad_relativa = models.DecimalField(max_digits=5, decimal_places=2)
    luz_estado = models.CharField(
        max_length=10,
        choices=LUZ_ESTADO_CHOICES,
        null=True,
        blank=True,
        verbose_name="Estado de la luz",
        help_text="Calculado automáticamente según el fotoperiodo activo al momento de la medición.",
    )
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mediciones_creadas')

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Medición de ambiente"
        verbose_name_plural = "Mediciones de ambiente"

    def __str__(self):
        return f"{self.cultivo} — {self.timestamp:%d/%m %H:%M} | {self.temperatura_c}°C {self.humedad_relativa}%HR"

    def save(self, *args, **kwargs):
        if self.luz_estado is None:
            from .utils import resolver_luz_estado_para_medicion
            self.luz_estado = resolver_luz_estado_para_medicion(self.cultivo, self.timestamp)
        super().save(*args, **kwargs)

    @property
    def vpd(self):
        """VPD en kPa — fórmula Magnus. Nunca se almacena en DB."""
        T = float(self.temperatura_c)
        HR = float(self.humedad_relativa)
        es = 0.6108 * math.exp(17.27 * T / (T + 237.3))
        return round(es * (1 - HR / 100), 3)

    @property
    def vpd_estado(self):
        """Ideal/alto/bajo según el rango de VPD de ParametroIdeal para la etapa del cultivo.

        Única fuente de verdad (ver también _evaluar_ambiente en views.py) — si no hay
        ParametroIdeal cargado para la etapa, no se puede clasificar.
        """
        v = self.vpd
        etapa = self.cultivo.estado
        param = cache.get_or_set(
            f"parametro_ideal:{etapa}",
            lambda: ParametroIdeal.objects.filter(etapa=etapa).first(),
            300,
        )
        if param is None:
            return None
        if float(param.vpd_min) <= v <= float(param.vpd_max):
            return "ideal"
        return "bajo" if v < float(param.vpd_min) else "alto"


class Nutriente(models.Model):
    ETAPA_CHOICES = [
        ("veg", "Vegetativo"),
        ("flora", "Floración"),
        ("aditivo", "Aditivo"),
    ]

    nombre = models.CharField(max_length=120)
    marca = models.CharField(max_length=120, blank=True)
    npk = models.CharField(max_length=30, blank=True, help_text="Ej: 25-2.8-6.9")
    etapa_recomendada = models.CharField(max_length=10, choices=ETAPA_CHOICES, default="veg")
    dosis_recomendada_min = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    dosis_recomendada_max = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["marca", "nombre"]
        verbose_name = "Nutriente"
        verbose_name_plural = "Nutrientes"

    def __str__(self):
        return f"{self.marca} {self.nombre}" if self.marca else self.nombre


class Riego(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="riegos")
    timestamp = models.DateTimeField(default=timezone.now)
    volumen_total_ml = models.PositiveIntegerField()
    volumen_por_planta_ml = models.PositiveIntegerField(null=True, blank=True)
    ph_agua = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    ec_solucion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    buscar_runoff = models.BooleanField(default=False)
    runoff_observado = models.BooleanField(default=False)
    ph_runoff = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="pH runoff")
    ec_runoff = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="EC runoff (mS/cm)")
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='riegos_creados')

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Riego"
        verbose_name_plural = "Riegos"

    def __str__(self):
        return f"Riego {self.cultivo} — {self.timestamp:%d/%m %H:%M} ({self.volumen_total_ml}ml)"


class NutrienteAplicado(models.Model):
    riego = models.ForeignKey(Riego, on_delete=models.CASCADE, related_name="nutrientes_aplicados")
    nutriente = models.ForeignKey(Nutriente, on_delete=models.PROTECT)
    dosis_g_por_litro = models.DecimalField(max_digits=6, decimal_places=3)

    class Meta:
        verbose_name = "Nutriente aplicado"
        verbose_name_plural = "Nutrientes aplicados"

    def __str__(self):
        return f"{self.nutriente} @ {self.dosis_g_por_litro}g/L"


class RiegoPlanta(models.Model):
    """Detalle de riego por planta individual dentro de una sesión de Riego."""
    riego = models.ForeignKey(Riego, on_delete=models.CASCADE, related_name="detalle_plantas")
    planta = models.ForeignKey(Planta, on_delete=models.CASCADE, related_name="riegos_detalle")
    volumen_ml = models.PositiveIntegerField(verbose_name="Volumen (ml)")
    runoff_observado = models.BooleanField(default=False)
    ph_runoff = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="pH runoff")
    ec_runoff = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="EC runoff (mS/cm)")
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ["planta__apodo"]
        unique_together = [("riego", "planta")]
        verbose_name = "Detalle de riego por planta"
        verbose_name_plural = "Detalles de riego por planta"

    def __str__(self):
        return f"{self.planta.apodo} — {self.volumen_ml}ml (riego #{self.riego_id})"


class Evento(models.Model):
    TIPO_CHOICES = [
        ("topping", "Topping"),
        ("lst", "LST"),
        ("defoliacion", "Defoliación"),
        ("transplante", "Transplante"),
        ("problema", "Problema"),
        ("diagnostico", "Diagnóstico"),
        ("ajuste_ambiente", "Ajuste de ambiente"),
        ("cambio_ciclo", "Cambio de ciclo"),
        ("otro", "Otro"),
    ]

    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="eventos")
    timestamp = models.DateTimeField(default=timezone.now)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descripcion = models.TextField()
    plantas_afectadas = models.ManyToManyField(Planta, blank=True, related_name="eventos")
    follow_up_fecha = models.DateField(null=True, blank=True)
    follow_up_descripcion = models.TextField(blank=True)
    follow_up_resuelto = models.BooleanField(default=False)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='eventos_creados')

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.timestamp:%d/%m/%Y}"


class MedicionPlanta(models.Model):
    ASPECTO_CHOICES = [
        ("bueno", "Bueno"),
        ("regular", "Regular"),
        ("malo", "Malo"),
    ]

    planta = models.ForeignKey(Planta, on_delete=models.CASCADE, related_name="mediciones")
    fecha = models.DateField(default=timezone.localdate)
    altura_cm = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    nudos_count = models.PositiveSmallIntegerField(null=True, blank=True)
    ancho_canopy_cm = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    aspecto_general = models.CharField(max_length=10, choices=ASPECTO_CHOICES, default="bueno")
    sintomas = models.TextField(blank=True)
    foto = models.ImageField(upload_to="plantas/%Y/%m/", null=True, blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mediciones_planta_creadas')

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Medición de planta"
        verbose_name_plural = "Mediciones de plantas"

    def __str__(self):
        return f"{self.planta.apodo} — {self.fecha}"


class Tarea(models.Model):
    PRIORIDAD_CHOICES = [
        ("urgente", "Urgente"),
        ("normal", "Normal"),
        ("baja", "Baja"),
    ]
    CATEGORIA_CHOICES = [
        ("riego", "Riego"),
        ("training", "Training"),
        ("mantenimiento", "Mantenimiento"),
        ("compra", "Compra"),
        ("observacion", "Observación"),
    ]

    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="tareas")
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    fecha_objetivo = models.DateField(null=True, blank=True)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default="normal")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default="observacion")
    completada = models.BooleanField(default=False)
    completada_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tareas_creadas')

    class Meta:
        ordering = ["completada", "fecha_objetivo", "-prioridad"]
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"

    def __str__(self):
        return self.titulo


class APIToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API Token"
        verbose_name_plural = "API Tokens"

    def __str__(self):
        return f"{self.user.username} — {self.created_at:%d/%m/%Y}"


class ParametroIdeal(models.Model):
    ETAPA_CHOICES = [
        ("plantula", "Plántula"),
        ("vegetativo", "Vegetativo"),
        ("floracion", "Floración"),
        ("secado", "Secado"),
    ]

    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, unique=True)
    temp_min = models.DecimalField(max_digits=5, decimal_places=1)
    temp_max = models.DecimalField(max_digits=5, decimal_places=1)
    hr_min = models.DecimalField(max_digits=5, decimal_places=1)
    hr_max = models.DecimalField(max_digits=5, decimal_places=1)
    ph_min = models.DecimalField(max_digits=4, decimal_places=2)
    ph_max = models.DecimalField(max_digits=4, decimal_places=2)
    ec_min = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ec_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    vpd_min = models.DecimalField(max_digits=4, decimal_places=2)
    vpd_max = models.DecimalField(max_digits=4, decimal_places=2)
    horas_luz = models.PositiveSmallIntegerField(null=True, blank=True)
    distancia_luz_min = models.PositiveSmallIntegerField(null=True, blank=True, help_text="cm")
    distancia_luz_max = models.PositiveSmallIntegerField(null=True, blank=True, help_text="cm")

    class Meta:
        verbose_name = "Parámetro ideal"
        verbose_name_plural = "Parámetros ideales"

    def __str__(self):
        return f"Parámetros — {self.get_etapa_display()}"


class PushSubscription(models.Model):
    """Suscripción a notificaciones push del navegador (Web Push API)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Suscripción push"
        verbose_name_plural = "Suscripciones push"

    def __str__(self):
        return f"{self.user.username} — {self.creado_en:%d/%m/%Y}"


POSICION_TENT_COORDS = {
    "centro":     (0.50, 0.50),
    "arriba_izq": (0.30, 0.30),
    "arriba_der": (0.70, 0.30),
    "abajo_izq":  (0.30, 0.70),
    "abajo_der":  (0.70, 0.70),
    "otro":       (0.50, 0.50),
}


class CanopySnapshot(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name='canopy_snapshots')
    creado_en = models.DateTimeField(auto_now_add=True)
    notas = models.TextField(blank=True)
    scrog_fill_pct = models.PositiveSmallIntegerField(default=0)
    scrog_cells = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = "Canopy Snapshot"
        verbose_name_plural = "Canopy Snapshots"

    def __str__(self):
        return f"{self.cultivo} — snapshot {self.creado_en:%d/%m/%Y %H:%M}"


class ColaPosicion(models.Model):
    snapshot = models.ForeignKey(CanopySnapshot, on_delete=models.CASCADE, related_name='colas')
    planta = models.ForeignKey(Planta, on_delete=models.CASCADE, related_name='posiciones_cola')
    indice = models.PositiveSmallIntegerField()
    x = models.FloatField()
    y = models.FloatField()

    class Meta:
        unique_together = [('snapshot', 'planta', 'indice')]
        ordering = ['planta', 'indice']
        verbose_name = "Posición de Cola"
        verbose_name_plural = "Posiciones de Colas"

    def __str__(self):
        return f"{self.planta.apodo} cola {self.indice} @ ({self.x:.2f}, {self.y:.2f})"


class MedicionEC(models.Model):
    TIPO_CHOICES = [
        ("entrada", "Agua de entrada"),
        ("solucion", "Solución nutritiva"),
        ("runoff", "Runoff / Drenaje"),
        ("sustrato", "Sustrato directo"),
    ]

    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="mediciones_ec")
    timestamp = models.DateTimeField(default=timezone.now)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="solucion")
    ph = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="pH")
    ec = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="EC (mS/cm)")
    temp_agua = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Temp. agua (°C)")
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mediciones_ec_creadas')

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Medición EC/pH"
        verbose_name_plural = "Mediciones EC/pH"

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.cultivo} ({self.timestamp:%d/%m %H:%M})"


# ── Módulo energético ─────────────────────────────────────────────────────────

class Equipo(models.Model):
    CATEGORIA_CHOICES = [
        ('lampara', 'Lámpara'),
        ('extractor', 'Extractor'),
        ('ventilador', 'Ventilador'),
        ('humidificador', 'Humidificador'),
        ('otro', 'Otro'),
    ]

    nombre = models.CharField(max_length=120)
    watts = models.DecimalField(max_digits=8, decimal_places=2)
    horas_dia = models.DecimalField(max_digits=4, decimal_places=2)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['categoria', 'nombre']
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'

    def __str__(self):
        return f"{self.nombre} ({self.watts}W)"

    @property
    def kwh_mes(self):
        return round(float(self.watts) / 1000 * float(self.horas_dia) * 30, 2)


class TarifaElectrica(models.Model):
    fecha_desde = models.DateField()
    precio_kwh = models.DecimalField(max_digits=10, decimal_places=4)
    distribuidora = models.CharField(max_length=100, default='Edesur')
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha_desde']
        verbose_name = 'Tarifa eléctrica'
        verbose_name_plural = 'Tarifas eléctricas'

    def __str__(self):
        return f"${self.precio_kwh}/kWh desde {self.fecha_desde} ({self.distribuidora})"


class CostoEnergetico(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name='costos_energeticos')
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='costos')
    tarifa = models.ForeignKey(TarifaElectrica, on_delete=models.PROTECT, related_name='costos')
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_desde']
        verbose_name = 'Costo energético'
        verbose_name_plural = 'Costos energéticos'

    def __str__(self):
        hasta = self.fecha_hasta or 'vigente'
        return f"{self.equipo.nombre} en {self.cultivo.nombre} ({self.fecha_desde} → {hasta})"


class LecturaMedidor(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name='lecturas_medidor')
    fecha = models.DateField()
    kwh_real = models.DecimalField(max_digits=10, decimal_places=2)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Lectura de medidor'
        verbose_name_plural = 'Lecturas de medidor'

    def __str__(self):
        return f"{self.cultivo.nombre} — {self.fecha} ({self.kwh_real} kWh)"
