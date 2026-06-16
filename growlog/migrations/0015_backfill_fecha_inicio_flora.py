from django.db import migrations


def backfill_fecha_inicio_flora(apps, schema_editor):
    Cultivo = apps.get_model("growlog", "Cultivo")
    CambioFotoperiodo = apps.get_model("growlog", "CambioFotoperiodo")

    for cultivo in Cultivo.objects.filter(fecha_inicio_flora__isnull=True):
        flip = None
        for cambio in CambioFotoperiodo.objects.filter(cultivo=cultivo).order_by("fecha_inicio"):
            try:
                horas_luz = int(cambio.fotoperiodo.split("/")[0])
            except (ValueError, IndexError):
                continue
            if horas_luz <= 12:
                flip = cambio
                break
        if flip:
            cultivo.fecha_inicio_flora = flip.fecha_inicio
            cultivo.save(update_fields=["fecha_inicio_flora"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("growlog", "0014_cultivo_fecha_inicio_flora"),
    ]

    operations = [
        migrations.RunPython(backfill_fecha_inicio_flora, noop),
    ]
