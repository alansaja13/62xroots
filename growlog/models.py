import math
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify


class Cultivo(models.Model):
    ESTADO_CHOICES = [
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
        return (timezone.localdate() - self.fecha_inicio).days


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
    apodo = models.CharField(max_length=60)
    strain = models.CharField(max_length=120, blank=True)
    posicion_tent = models.CharField(max_length=20, choices=POSICION_CHOICES, default="otro")
    dias_flora_estimados = models.PositiveSmallIntegerField(null=True, blank=True)
    indica_sativa_ratio = models.CharField(max_length=20, blank=True, help_text="Ej: 70/30")
    thc_estimado = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    yield_estimado_g = models.PositiveSmallIntegerField(null=True, blank=True)
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


class MedicionAmbiente(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="mediciones")
    timestamp = models.DateTimeField(default=timezone.now)
    temperatura_c = models.DecimalField(max_digits=5, decimal_places=2)
    humedad_relativa = models.DecimalField(max_digits=5, decimal_places=2)
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mediciones_creadas')

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Medición de ambiente"
        verbose_name_plural = "Mediciones de ambiente"

    def __str__(self):
        return f"{self.cultivo} — {self.timestamp:%d/%m %H:%M} | {self.temperatura_c}°C {self.humedad_relativa}%HR"

    @property
    def vpd(self):
        """VPD en kPa — fórmula Magnus. Nunca se almacena en DB."""
        T = float(self.temperatura_c)
        HR = float(self.humedad_relativa)
        es = 0.6108 * math.exp(17.27 * T / (T + 237.3))
        return round(es * (1 - HR / 100), 3)

    @property
    def vpd_estado(self):
        v = self.vpd
        etapa = self.cultivo.estado
        if etapa == "vegetativo":
            if 0.8 <= v <= 1.2:
                return "ideal"
            return "bajo" if v < 0.8 else "alto"
        else:
            if 1.0 <= v <= 1.5:
                return "ideal"
            return "bajo" if v < 1.0 else "alto"


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
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API Token"
        verbose_name_plural = "API Tokens"

    def __str__(self):
        return f"{self.user.username} — {self.token}"


class ParametroIdeal(models.Model):
    ETAPA_CHOICES = [
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
