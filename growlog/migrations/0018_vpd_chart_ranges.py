from decimal import Decimal
from django.db import migrations


VPD_RANGES = {
    "vegetativo": (Decimal("0.80"), Decimal("0.95")),
    "floracion": (Decimal("0.96"), Decimal("1.15")),
}


def actualizar_rangos_vpd(apps, schema_editor):
    ParametroIdeal = apps.get_model("growlog", "ParametroIdeal")
    for etapa, (vpd_min, vpd_max) in VPD_RANGES.items():
        ParametroIdeal.objects.filter(etapa=etapa).update(vpd_min=vpd_min, vpd_max=vpd_max)


def revertir_rangos_vpd(apps, schema_editor):
    ParametroIdeal = apps.get_model("growlog", "ParametroIdeal")
    ParametroIdeal.objects.filter(etapa="vegetativo").update(vpd_min=Decimal("0.8"), vpd_max=Decimal("1.2"))
    ParametroIdeal.objects.filter(etapa="floracion").update(vpd_min=Decimal("1.0"), vpd_max=Decimal("1.5"))


class Migration(migrations.Migration):

    dependencies = [
        ("growlog", "0017_riegoplanta"),
    ]

    operations = [
        migrations.RunPython(actualizar_rangos_vpd, revertir_rangos_vpd),
    ]
