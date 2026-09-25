import io
import json

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class OwnershipMigrationTests(TransactionTestCase):
    def test_migra_autores_y_no_asigna_recursos_ambiguos_ni_comparte_por_defecto(self):
        before = [("growlog", "0023_split_parametro_ideal_veg_flora")]
        after = [("growlog", "0025_asignar_propietarios")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            User = apps.get_model("auth", "User")
            Cultivo = apps.get_model("growlog", "Cultivo")
            Equipo = apps.get_model("growlog", "Equipo")
            Tarifa = apps.get_model("growlog", "TarifaElectrica")
            Costo = apps.get_model("growlog", "CostoEnergetico")
            a = User.objects.create(username="a")
            b = User.objects.create(username="b")
            User.objects.create(username="invitado-antiguo", is_staff=False)
            hoy = timezone.localdate()
            c1 = Cultivo.objects.create(nombre="Uno", slug="uno", creado_por=a, fecha_inicio=hoy)
            c2 = Cultivo.objects.create(nombre="Dos", slug="dos", creado_por=b, fecha_inicio=hoy)
            orphan = Cultivo.objects.create(nombre="Sin autor", slug="sin-autor", fecha_inicio=hoy)
            one = Equipo.objects.create(nombre="Propio", watts=100, horas_dia=18)
            shared = Equipo.objects.create(nombre="Ambiguo", watts=100, horas_dia=18)
            mixed = Equipo.objects.create(nombre="Con cultivo sin autor", watts=100, horas_dia=18)
            unused = Equipo.objects.create(nombre="Sin uso", watts=100, horas_dia=18)
            tariff = Tarifa.objects.create(fecha_desde=hoy, precio_kwh=10)
            for cultivo, equipo in ((c1, one), (c1, shared), (c2, shared), (c1, mixed), (orphan, mixed)):
                Costo.objects.create(cultivo=cultivo, equipo=equipo, tarifa=tariff, fecha_desde=hoy)
            output = io.StringIO()
            call_command("auditar_actualizacion", stdout=output)
            audit = json.loads(output.getvalue())
            self.assertFalse(audit["esquema_con_propietarios"])
            self.assertEqual(audit["revisar_ids"]["cultivos_sin_propietario"], [orphan.pk])
            self.assertEqual(audit["revisar_ids"]["equipo_sin_propietario_inequivoco"],
                             sorted([shared.pk, mixed.pk, unused.pk]))
            self.assertIn("0025_asignar_propietarios", audit["migraciones_growlog_pendientes"])
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            Cultivo = apps.get_model("growlog", "Cultivo")
            Equipo = apps.get_model("growlog", "Equipo")
            self.assertEqual(Cultivo.objects.get(pk=c1.pk).propietario_id, a.pk)
            self.assertIsNone(Cultivo.objects.get(pk=orphan.pk).propietario_id)
            self.assertEqual(Equipo.objects.get(pk=one.pk).propietario_id, a.pk)
            for equipo in (shared, mixed, unused):
                self.assertIsNone(Equipo.objects.get(pk=equipo.pk).propietario_id)
            self.assertIsNone(apps.get_model("growlog", "TarifaElectrica").objects.get(pk=tariff.pk).propietario_id)
            self.assertEqual(apps.get_model("growlog", "CultivoMiembro").objects.count(), 0)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
