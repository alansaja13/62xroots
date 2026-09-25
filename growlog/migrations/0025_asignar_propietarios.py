from django.db import migrations
from django.db.models import F


def asignar_propietarios(apps, schema_editor):
    alias = schema_editor.connection.alias
    Cultivo = apps.get_model("growlog", "Cultivo")
    Cultivo.objects.using(alias).filter(propietario__isnull=True).update(propietario_id=F("creado_por_id"))
    # No conceder acceso a invitados antiguos sin una selección explícita.
    # Recursos sin propietario inequívoco quedan para revisión administrativa.
    for nombre in ("Equipo", "TarifaElectrica"):
        Model = apps.get_model("growlog", nombre)
        for recurso in Model.objects.using(alias).filter(propietario__isnull=True).iterator():
            owners = set(recurso.costos.using(alias)
                         .values_list("cultivo__propietario_id", flat=True))
            if len(owners) == 1 and None not in owners:
                Model.objects.using(alias).filter(pk=recurso.pk).update(propietario_id=owners.pop())


class Migration(migrations.Migration):
    dependencies = [("growlog", "0024_cultivo_propietario_equipo_propietario_and_more")]
    operations = [migrations.RunPython(asignar_propietarios, migrations.RunPython.noop)]
