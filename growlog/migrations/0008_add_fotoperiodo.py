import zoneinfo
from datetime import time as dtime

import django.db.models.deletion
from django.db import migrations, models


ARGENTINA_TZ = zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires")
MIGRATION_NOTES = "Migración inicial automática — 0008"


def _calcular_luz_estado(timestamp, hora_lights_on, fotoperiodo):
    if timestamp.tzinfo is None:
        ts_local = timestamp.replace(tzinfo=ARGENTINA_TZ)
    else:
        ts_local = timestamp.astimezone(ARGENTINA_TZ)
    horas_luz = int(fotoperiodo.split("/")[0])
    current_min = ts_local.hour * 60 + ts_local.minute
    on_min = hora_lights_on.hour * 60 + hora_lights_on.minute
    off_min = (on_min + horas_luz * 60) % (24 * 60)
    if on_min < off_min:
        return "on" if on_min <= current_min < off_min else "off"
    else:
        return "on" if current_min >= on_min or current_min < off_min else "off"


def backfill_fotoperiodo(apps, schema_editor):
    Cultivo = apps.get_model("growlog", "Cultivo")
    MedicionAmbiente = apps.get_model("growlog", "MedicionAmbiente")
    CambioFotoperiodo = apps.get_model("growlog", "CambioFotoperiodo")

    for cultivo in Cultivo.objects.all():
        CambioFotoperiodo.objects.get_or_create(
            cultivo=cultivo,
            fecha_inicio=cultivo.fecha_inicio,
            defaults={
                "fotoperiodo": "18/6",
                "hora_lights_on": dtime(17, 0),
                "notas": MIGRATION_NOTES,
            },
        )

    to_update = []
    for medicion in MedicionAmbiente.objects.select_related("cultivo").iterator():
        ts = medicion.timestamp
        ts_local = ts.astimezone(ARGENTINA_TZ) if ts.tzinfo else ts.replace(tzinfo=ARGENTINA_TZ)
        cambio = CambioFotoperiodo.objects.filter(
            cultivo=medicion.cultivo,
            fecha_inicio__lte=ts_local.date(),
        ).order_by("-fecha_inicio").first()
        if cambio:
            medicion.luz_estado = _calcular_luz_estado(ts, cambio.hora_lights_on, cambio.fotoperiodo)
            to_update.append(medicion)

    if to_update:
        MedicionAmbiente.objects.bulk_update(to_update, ["luz_estado"])


def reverse_backfill(apps, schema_editor):
    CambioFotoperiodo = apps.get_model("growlog", "CambioFotoperiodo")
    MedicionAmbiente = apps.get_model("growlog", "MedicionAmbiente")
    CambioFotoperiodo.objects.filter(notas=MIGRATION_NOTES).delete()
    MedicionAmbiente.objects.update(luz_estado=None)


class Migration(migrations.Migration):

    dependencies = [
        ("growlog", "0007_security_token_hash_planta_uuid"),
    ]

    operations = [
        migrations.CreateModel(
            name="CambioFotoperiodo",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cultivo", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cambios_fotoperiodo",
                    to="growlog.cultivo",
                )),
                ("fotoperiodo", models.CharField(
                    help_text="Formato N/M donde N+M=24. Ej: 18/6, 12/12",
                    max_length=5,
                    verbose_name="Fotoperiodo",
                )),
                ("hora_lights_on", models.TimeField(
                    help_text="Hora local (Argentina) en que se enciende la luz",
                    verbose_name="Hora de encendido",
                )),
                ("fecha_inicio", models.DateField(
                    help_text="Fecha desde la cual rige este fotoperiodo",
                    verbose_name="Fecha de inicio",
                )),
                ("notas", models.TextField(blank=True, verbose_name="Notas")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Cambio de fotoperiodo",
                "verbose_name_plural": "Cambios de fotoperiodo",
                "ordering": ["-fecha_inicio"],
            },
        ),
        migrations.AddConstraint(
            model_name="cambiofotoperiodo",
            constraint=models.UniqueConstraint(
                fields=["cultivo", "fecha_inicio"],
                name="unique_cultivo_fecha_inicio",
            ),
        ),
        migrations.AddField(
            model_name="medicionambiente",
            name="luz_estado",
            field=models.CharField(
                blank=True,
                choices=[("on", "Luz prendida"), ("off", "Luz apagada")],
                help_text="Calculado automáticamente según el fotoperiodo activo al momento de la medición.",
                max_length=10,
                null=True,
                verbose_name="Estado de la luz",
            ),
        ),
        migrations.RunPython(backfill_fotoperiodo, reverse_backfill),
    ]
