import io
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage, storages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .models import ClaveRegistroLocal, Cultivo, CultivoMiembro, Equipo, RegistroRecibido


class ReleaseAuditTests(TestCase):
    def test_backup_rechaza_filesystem_efimero_antes_de_exportar(self):
        with self.subTest("No necesita crear archivos para rechazar el destino"):
            directory = str(Path.cwd() / "test-backup-not-written")
            storage = FileSystemStorage(location=directory)
            with patch("growlog.management.commands.backup_db.storages", {"backups": storage}), \
                 patch("growlog.management.commands.backup_db.call_command") as dump, \
                 patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_ID": "test", "RAILWAY_VOLUME_MOUNT_PATH": ""}):
                with self.assertRaisesMessage(CommandError, "No se exportaron datos"):
                    call_command("backup_db", stdout=io.StringIO())
                dump.assert_not_called()

    def test_backup_rechaza_directorio_fuera_del_volumen(self):
        with self.subTest("Un prefijo de ruta no alcanza para pertenecer al volumen"):
            directory = str(Path.cwd() / "test-volume-not-written")
            storage = FileSystemStorage(location=directory + "-outside")
            with patch("growlog.management.commands.backup_db.storages", {"backups": storage}), \
                 patch("growlog.management.commands.backup_db.call_command") as dump, \
                 patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_ID": "test", "RAILWAY_VOLUME_MOUNT_PATH": directory}):
                with self.assertRaises(CommandError):
                    call_command("backup_db", stdout=io.StringIO())
                dump.assert_not_called()

    def test_backup_admite_directorio_dentro_del_volumen(self):
        directory = str(Path.cwd() / "test-volume-not-written")
        storage = FileSystemStorage(location=str(Path(directory) / "backups"))
        with patch("growlog.management.commands.backup_db.storages", {"backups": storage}), \
             patch("growlog.management.commands.backup_db.call_command") as dump, \
             patch.object(storage, "save", return_value="backup.json") as save, \
             patch.object(storage, "size", return_value=2), \
             patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_ID": "test", "RAILWAY_VOLUME_MOUNT_PATH": directory}):
            call_command("backup_db", stdout=io.StringIO())
            dump.assert_called_once()
            save.assert_called_once()

    def test_auditoria_informa_sin_mutar_ni_exponer_claves(self):
        owner = User.objects.create_user(username="private-name", password="private-password")
        c = Cultivo.objects.create(nombre="private-cultivo", fecha_inicio=timezone.localdate(), propietario=owner)
        orphan = Cultivo.objects.create(nombre="sin dueño", fecha_inicio=timezone.localdate())
        resource = Equipo.objects.create(nombre="sin asignar", watts=100, horas_dia=12)
        key = ClaveRegistroLocal.objects.create(usuario=owner)
        output = io.StringIO()
        call_command("auditar_actualizacion", stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["revisar_ids"]["cultivos_sin_propietario"], [orphan.pk])
        self.assertEqual(report["revisar_ids"]["equipo_sin_propietario_inequivoco"], [resource.pk])
        self.assertEqual(report["migraciones_growlog_pendientes"], [])
        for secret in (owner.username, c.nombre, key.clave, owner.password):
            self.assertNotIn(secret, output.getvalue())
        c.refresh_from_db()
        self.assertEqual(c.propietario_id, owner.pk)

    def test_modo_estricto_falla_si_hay_revision(self):
        Cultivo.objects.create(nombre="sin dueño", fecha_inicio=timezone.localdate())
        with self.assertRaises(CommandError):
            call_command("auditar_actualizacion", fail_on_review=True, stdout=io.StringIO())


class BackupRestoreTests(TransactionTestCase):
    def test_backup_privado_restaura_permisos_clave_y_recibo(self):
        owner = User.objects.create_user(username="restore-owner")
        editor = User.objects.create_user(username="restore-editor")
        c = Cultivo.objects.create(nombre="Restaurable", fecha_inicio=timezone.localdate(), propietario=owner)
        CultivoMiembro.objects.create(cultivo=c, usuario=editor, rol="editor")
        key = ClaveRegistroLocal.objects.create(usuario=editor)
        RegistroRecibido.objects.create(usuario=editor, cultivo=c,
            operacion_id="9b8d9c8e-73f8-4de6-b7c6-a0cc111aad90", contenido_hash="a" * 64,
            resultado={"registro_id": 9, "tipo": "evento"})
        storage = storages["backups"]
        before = set(storage.listdir("")[1])
        call_command("backup_db", stdout=io.StringIO())
        created = set(storage.listdir("")[1]) - before
        self.assertEqual(len(created), 1)
        name = created.pop()
        try:
            with storage.open(name) as source:
                fixture = source.read().decode("utf-8")
            # Solo la base efímera de TransactionTestCase: jamás el entorno real.
            call_command("flush", interactive=False, verbosity=0)
            with patch("sys.stdin", io.StringIO(fixture)):
                call_command("loaddata", "-", format="json", verbosity=0)
            restored = Cultivo.objects.get(nombre="Restaurable")
            self.assertEqual(restored.propietario.username, "restore-owner")
            self.assertEqual(restored.miembros.get().rol, "editor")
            self.assertEqual(ClaveRegistroLocal.objects.get(usuario__username="restore-editor").clave, key.clave)
            self.assertEqual(RegistroRecibido.objects.get().resultado, {"registro_id": 9, "tipo": "evento"})
        finally:
            storage.delete(name)
