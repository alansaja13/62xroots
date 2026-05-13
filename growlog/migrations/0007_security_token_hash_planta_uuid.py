import hashlib
import uuid
from django.db import migrations, models


def assign_planta_uuids(apps, schema_editor):
    Planta = apps.get_model('growlog', 'Planta')
    for planta in Planta.objects.filter(uuid__isnull=True):
        planta.uuid = uuid.uuid4()
        planta.save(update_fields=['uuid'])


def hash_existing_tokens(apps, schema_editor):
    """Hashea los tokens UUID existentes. Los clientes ya emitidos siguen funcionando
    enviando el UUID como Bearer token (se hashea en require_token antes del lookup)."""
    APIToken = apps.get_model('growlog', 'APIToken')
    for token_obj in APIToken.objects.all():
        token_obj.token_hash = hashlib.sha256(str(token_obj.token).encode()).hexdigest()
        token_obj.save(update_fields=['token_hash'])


class Migration(migrations.Migration):

    dependencies = [
        ('growlog', '0006_backfill_cultivo_slugs'),
    ]

    operations = [
        # ── H-1: Agregar campo token_hash (nullable para la data migration) ──
        migrations.AddField(
            model_name='apitoken',
            name='token_hash',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        # Poblar token_hash desde los tokens UUID existentes
        migrations.RunPython(hash_existing_tokens, migrations.RunPython.noop),
        # Hacer token_hash requerido y único
        migrations.AlterField(
            model_name='apitoken',
            name='token_hash',
            field=models.CharField(max_length=64, unique=True),
        ),
        # Eliminar el campo UUID en claro
        migrations.RemoveField(
            model_name='apitoken',
            name='token',
        ),
        # ── M-1: Agregar UUID a Planta (3 pasos para compatibilidad con SQLite) ──
        # Paso 1: campo nullable sin unique
        migrations.AddField(
            model_name='planta',
            name='uuid',
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        # Paso 2: poblar con UUIDs únicos fila por fila
        migrations.RunPython(assign_planta_uuids, migrations.RunPython.noop),
        # Paso 3: hacer el campo requerido y único
        migrations.AlterField(
            model_name='planta',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
