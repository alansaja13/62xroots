from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("growlog", "0008_add_fotoperiodo"),
    ]

    operations = [
        migrations.AddField(
            model_name="cultivo",
            name="dias_veg_estimados",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Días totales esperados en etapa vegetativa (desde inicio).",
                null=True,
                verbose_name="Días de vegetativo estimados",
            ),
        ),
        migrations.AddField(
            model_name="cultivo",
            name="dias_flora_estimados",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Días esperados en etapa de floración.",
                null=True,
                verbose_name="Días de floración estimados",
            ),
        ),
    ]
