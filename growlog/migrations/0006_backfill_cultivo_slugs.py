from django.db import migrations
from django.utils.text import slugify


def generate_slugs(apps, schema_editor):
    Cultivo = apps.get_model("growlog", "Cultivo")
    used = set()
    for cultivo in Cultivo.objects.all():
        base = slugify(cultivo.nombre)
        slug, n = base, 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        cultivo.slug = slug
        cultivo.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("growlog", "0005_add_slug_to_cultivo"),
    ]

    operations = [
        migrations.RunPython(generate_slugs, migrations.RunPython.noop),
    ]
