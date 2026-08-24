import os

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Migración única: sube todos los archivos de MEDIA_ROOT (disco/volume local) "
        "al storage por defecto configurado (R2). Correr una sola vez después de "
        "configurar las variables R2_* en producción."
    )

    def handle(self, *args, **options):
        if not getattr(settings, "R2_BUCKET", None):
            raise CommandError(
                "R2_BUCKET no está configurado — este comando solo tiene sentido "
                "una vez que el storage por defecto ya apunta a R2."
            )

        media_root = settings.MEDIA_ROOT
        if not os.path.isdir(media_root):
            self.stdout.write("No hay MEDIA_ROOT local — nada para migrar.")
            return

        subidos = saltados = 0
        for dirpath, _dirnames, filenames in os.walk(media_root):
            for filename in filenames:
                local_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(local_path, media_root).replace(os.sep, "/")

                if default_storage.exists(rel_path):
                    saltados += 1
                    continue

                with open(local_path, "rb") as f:
                    default_storage.save(rel_path, File(f))
                subidos += 1
                self.stdout.write(f"  subido: {rel_path}")

        self.stdout.write(self.style.SUCCESS(f"Listo — {subidos} archivo(s) subido(s), {saltados} ya existían en R2."))
