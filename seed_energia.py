"""
Seed de datos energéticos — equipos y tarifa inicial.
Correr con: py -3 manage.py shell < seed_energia.py
"""
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from datetime import date
from growlog.models import Equipo, TarifaElectrica, CostoEnergetico, Cultivo

# ── Tarifa inicial ─────────────────────────────────────────────────────────────
tarifa, created = TarifaElectrica.objects.get_or_create(
    fecha_desde=date(2026, 5, 1),
    defaults=dict(
        precio_kwh="202.0000",
        distribuidora="Edesur",
        notas="Tarifa residencial vigente desde mayo 2026.",
    ),
)
if created:
    print(f"[OK] Tarifa creada: ${tarifa.precio_kwh}/kWh desde {tarifa.fecha_desde}")
else:
    print(f"[--] Tarifa ya existia: ${tarifa.precio_kwh}/kWh")

# ── Equipos ────────────────────────────────────────────────────────────────────
equipos_data = [
    dict(nombre="Lampara COB",               watts="314",  horas_dia="12", categoria="lampara"),
    dict(nombre="Extractor lineal 4 3vel",   watts="110",  horas_dia="24", categoria="extractor"),
    dict(nombre="Ventiladores PC 120mm x2",  watts="24",   horas_dia="24", categoria="ventilador"),
    dict(nombre="Clip Garden HighPro",       watts="15",   horas_dia="24", categoria="ventilador"),
    dict(nombre="Humidificador Gadnic K6",   watts="25",   horas_dia="24", categoria="humidificador"),
    dict(nombre="Lampara plantas 50W",       watts="50",   horas_dia="18", categoria="lampara"),
]

equipos_creados = []
for data in equipos_data:
    equipo, created = Equipo.objects.get_or_create(
        nombre=data["nombre"],
        defaults=data,
    )
    equipos_creados.append(equipo)
    estado = "[OK]" if created else "[--]"
    accion = "creado" if created else "ya existia"
    print(f"{estado} Equipo {accion}: {equipo} | {equipo.kwh_mes} kWh/mes")

# ── Resumen de consumo ─────────────────────────────────────────────────────────
total_kwh = sum(e.kwh_mes for e in equipos_creados)
precio = float(tarifa.precio_kwh)
print(f"\n-- Consumo estimado con tarifa actual --")
for e in equipos_creados:
    costo = e.kwh_mes * precio
    print(f"  {e.nombre:<35} {e.kwh_mes:>7.1f} kWh/mes  ->  ${costo:>10,.0f}/mes")
print(f"  {'TOTAL':<35} {total_kwh:>7.1f} kWh/mes  ->  ${total_kwh * precio:>10,.0f}/mes")

# ── Vincular al cultivo activo (opcional) ──────────────────────────────────────
cultivo_activo = Cultivo.objects.filter(archivado=False).order_by('-fecha_inicio').first()
if cultivo_activo:
    print(f"\n-- Vinculando equipos al cultivo '{cultivo_activo.nombre}' --")
    vinculados = 0
    for equipo in equipos_creados:
        _, created = CostoEnergetico.objects.get_or_create(
            cultivo=cultivo_activo,
            equipo=equipo,
            fecha_hasta__isnull=True,
            defaults=dict(
                tarifa=tarifa,
                fecha_desde=cultivo_activo.fecha_inicio,
            ),
        )
        if created:
            vinculados += 1
    ya = len(equipos_creados) - vinculados
    print(f"  [OK] {vinculados} equipos vinculados ({ya} ya existian)")
else:
    print("\n[--] No hay cultivo activo -- vincula los equipos desde el admin (/admin/growlog/costoenergetico/add/)")

print("\n[OK] Seed energetico completo.")
