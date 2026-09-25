import io
import os
from datetime import datetime
from pathlib import Path
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, storages
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Exporta datos al almacenamiento privado de backups, separado de las fotos"

    def handle(self, *args, **options):
        backup_storage = storages["backups"]
        if os.environ.get("RAILWAY_ENVIRONMENT_ID") and isinstance(backup_storage, FileSystemStorage):
            mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
            if not mount or not Path(backup_storage.location).resolve().is_relative_to(Path(mount).resolve()):
                raise CommandError(
                    "Backup cancelado: el directorio de backups no está dentro del volumen "
                    "de Railway. Configurá BACKUP_ROOT dentro de RAILWAY_VOLUME_MOUNT_PATH "
                    "o un storage privado persistente. No se exportaron datos."
                )
        buffer = io.StringIO()
        call_command("dumpdata", "--natural-foreign", "--natural-primary", "--indent", "2", stdout=buffer)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"backup_{timestamp}.json"
        saved_name = backup_storage.save(name, ContentFile(buffer.getvalue().encode("utf-8")))

        size_kb = backup_storage.size(saved_name) / 1024
        self.stdout.write(self.style.SUCCESS(f"Backup guardado: {saved_name} ({size_kb:.1f} KB)"))
