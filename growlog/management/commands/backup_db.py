import io
from datetime import datetime
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exporta todos los datos a un archivo JSON en backups/ del storage por defecto (R2 en producción)"

    def handle(self, *args, **options):
        buffer = io.StringIO()
        call_command("dumpdata", "--natural-foreign", "--natural-primary", "--indent", "2", stdout=buffer)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"backups/backup_{timestamp}.json"
        saved_name = default_storage.save(name, ContentFile(buffer.getvalue().encode("utf-8")))

        size_kb = default_storage.size(saved_name) / 1024
        self.stdout.write(self.style.SUCCESS(f"Backup guardado: {saved_name} ({size_kb:.1f} KB)"))
