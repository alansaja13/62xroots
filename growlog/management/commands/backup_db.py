import os
from datetime import datetime
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exporta todos los datos a un archivo JSON en la carpeta backups/"

    def handle(self, *args, **options):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        backup_dir = os.path.join(base_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(backup_dir, f"backup_{timestamp}.json")

        with open(filename, "w", encoding="utf-8") as f:
            call_command("dumpdata", "--natural-foreign", "--natural-primary", "--indent", "2", stdout=f)

        size_kb = os.path.getsize(filename) / 1024
        self.stdout.write(self.style.SUCCESS(f"Backup guardado: {filename} ({size_kb:.1f} KB)"))
