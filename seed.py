"""
Script de seed: corre con `py -3 manage.py shell < seed.py`
Crea el cultivo actual, plantas, parámetros ideales y datos demo.
"""
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from datetime import date, timedelta
from django.utils import timezone
from growlog.models import (
    Cultivo, Planta, MedicionAmbiente, ParametroIdeal,
    Nutriente, Tarea,
)

# ── Parámetros ideales ──────────────────────────────────────────────────────
ParametroIdeal.objects.get_or_create(
    etapa="plantula",
    defaults=dict(
        temp_min=22, temp_max=26,
        hr_min=65, hr_max=75,
        ph_min=6.0, ph_max=6.8,
        ec_min=0.4, ec_max=0.8,
        vpd_min=0.40, vpd_max=0.80,
        horas_luz=18,
        distancia_luz_min=50, distancia_luz_max=70,
    ),
)
ParametroIdeal.objects.get_or_create(
    etapa="vegetativo",
    defaults=dict(
        temp_min=22, temp_max=28,
        hr_min=50, hr_max=70,
        ph_min=6.0, ph_max=6.8,
        ec_min=0.8, ec_max=1.4,
        vpd_min=0.80, vpd_max=0.95,
        horas_luz=18,
        distancia_luz_min=40, distancia_luz_max=60,
    ),
)
ParametroIdeal.objects.get_or_create(
    etapa="floracion",
    defaults=dict(
        temp_min=20, temp_max=26,
        hr_min=40, hr_max=55,
        ph_min=6.0, ph_max=6.8,
        ec_min=1.2, ec_max=2.0,
        vpd_min=0.96, vpd_max=1.15,
        horas_luz=12,
        distancia_luz_min=35, distancia_luz_max=50,
    ),
)
ParametroIdeal.objects.get_or_create(
    etapa="secado",
    defaults=dict(
        temp_min=15, temp_max=18,
        hr_min=58, hr_max=62,
        ph_min=6.0, ph_max=6.8,
        vpd_min=0.60, vpd_max=0.90,
        horas_luz=0,
    ),
)
print("✓ Parámetros ideales cargados")

# ── Nutrientes ───────────────────────────────────────────────────────────────
for n in [
    dict(nombre="Grow", marca="BioBizz", npk="4-3-6", etapa_recomendada="veg",
         dosis_recomendada_min=1, dosis_recomendada_max=4),
    dict(nombre="Bloom", marca="BioBizz", npk="2-7-4", etapa_recomendada="flora",
         dosis_recomendada_min=1, dosis_recomendada_max=4),
    dict(nombre="Top Max", marca="BioBizz", npk="0-1-1", etapa_recomendada="aditivo",
         dosis_recomendada_min=1, dosis_recomendada_max=3),
    dict(nombre="Bio Heaven", marca="BioBizz", npk="0-0-0", etapa_recomendada="aditivo",
         dosis_recomendada_min=1, dosis_recomendada_max=2),
]:
    Nutriente.objects.get_or_create(nombre=n["nombre"], marca=n["marca"], defaults=n)
print("✓ Nutrientes cargados")

# ── Cultivo actual ────────────────────────────────────────────────────────────
cultivo, created = Cultivo.objects.get_or_create(
    nombre="Fancy Gummy + Satélite #1",
    defaults=dict(
        fecha_inicio=date.today() - timedelta(days=13),
        estado="vegetativo",
        carpa_dimensiones="80×80×200 cm",
        sustrato="BioBizz Light-Mix",
        lampara_modelo="COB LED",
        lampara_watts_reales=300,
        notas="6 plantas: 5x Fancy Gummy + 1x Satélite. Día 13 desde trasplante.",
    ),
)
if created:
    print(f"✓ Cultivo creado: {cultivo}")
else:
    print(f"→ Cultivo ya existía: {cultivo}")

# ── Plantas ───────────────────────────────────────────────────────────────────
plantas_data = [
    ("FG-1", "Fancy Gummy", "arriba_izq"),
    ("FG-2", "Fancy Gummy", "arriba_der"),
    ("FG-3", "Fancy Gummy", "centro"),
    ("FG-4", "Fancy Gummy", "abajo_izq"),
    ("FG-5", "Fancy Gummy", "abajo_der"),
    ("SAT-1", "Satélite", "otro"),
]
for apodo, strain, pos in plantas_data:
    Planta.objects.get_or_create(
        cultivo=cultivo, apodo=apodo,
        defaults=dict(strain=strain, posicion_tent=pos),
    )
print(f"✓ {len(plantas_data)} plantas cargadas")

# ── Medición demo ─────────────────────────────────────────────────────────────
if not cultivo.mediciones.exists():
    MedicionAmbiente.objects.create(
        cultivo=cultivo,
        temperatura_c=25.5,
        humedad_relativa=62,
        notas="Primera medición — seed inicial",
    )
    print("✓ Medición demo cargada")

# ── Tareas iniciales ──────────────────────────────────────────────────────────
tareas = [
    ("Revisar pH del agua próximo riego", "riego", "normal", date.today() + timedelta(days=1)),
    ("Medir altura de las plantas", "observacion", "normal", date.today() + timedelta(days=2)),
    ("Verificar distancia de lámpara", "mantenimiento", "baja", date.today() + timedelta(days=3)),
]
for titulo, cat, prio, fecha in tareas:
    Tarea.objects.get_or_create(
        cultivo=cultivo, titulo=titulo,
        defaults=dict(categoria=cat, prioridad=prio, fecha_objetivo=fecha),
    )
print(f"✓ Tareas iniciales cargadas")
print("\n🌱 Seed completo. Corré el server con: py -3 manage.py runserver")
