from django.db import migrations


def set_alan_as_author(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    try:
        alan = User.objects.get(username='alan')
    except User.DoesNotExist:
        return

    for model_name in ('Cultivo', 'Planta', 'Riego', 'MedicionAmbiente',
                       'MedicionPlanta', 'Evento', 'Tarea'):
        Model = apps.get_model('growlog', model_name)
        Model.objects.filter(creado_por__isnull=True).update(creado_por=alan)


class Migration(migrations.Migration):

    dependencies = [
        ('growlog', '0003_creado_por'),
    ]

    operations = [
        migrations.RunPython(set_alan_as_author, migrations.RunPython.noop),
    ]
