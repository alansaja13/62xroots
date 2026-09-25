from django.core.management import call_command
from django.db import migrations


def crear_tabla_cache(apps, schema_editor):
    # createcachetable es idempotente y respeta CACHES: en tests (locmem) no hace nada.
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [("growlog", "0027_claveregistrolocal")]
    operations = [migrations.RunPython(crear_tabla_cache, migrations.RunPython.noop)]
