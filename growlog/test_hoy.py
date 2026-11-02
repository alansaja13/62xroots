from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .models import Cultivo, CultivoMiembro, Evento, MedicionAmbiente, ParametroIdeal, Riego, Tarea
from .services.hoy import resumen_hoy


class HoyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="hoy-owner")
        self.reader = User.objects.create_user(username="hoy-reader")
        self.now = datetime(2026, 9, 24, 12, tzinfo=dt_timezone.utc)
        self.today = timezone.localdate(self.now)
        self.c = Cultivo.objects.create(nombre="Ciclo visible", fecha_inicio=self.today, propietario=self.user)

    def tarea(self, **kwargs):
        return Tarea.objects.create(cultivo=self.c, titulo="Revisar sensor", **kwargs)

    def medir(self, cultivo=None, **kwargs):
        return MedicionAmbiente.objects.create(cultivo=cultivo or self.c, temperatura_c=24,
            humedad_relativa=60, luz_estado="on", **kwargs)

    def test_vence_hoy_atrasadas_urgentes_y_seguimientos_sin_completadas(self):
        vieja = self.tarea(fecha_objetivo=self.today - timedelta(days=1))
        normal = self.tarea(fecha_objetivo=self.today)
        urgente = self.tarea(fecha_objetivo=self.today, prioridad="urgente")
        self.tarea(fecha_objetivo=self.today, completada=True)
        self.tarea(fecha_objetivo=self.today + timedelta(days=1))
        self.tarea()
        evento = Evento.objects.create(cultivo=self.c, tipo="otro", descripcion="Controlar hojas",
            follow_up_fecha=self.today - timedelta(days=2))
        result = resumen_hoy(self.user, ahora=self.now)
        self.assertEqual([(i["tipo"], i["pk"]) for i in result["atencion"]],
                         [("Seguimiento", evento.pk), ("Tarea", vieja.pk), ("Tarea", urgente.pk), ("Tarea", normal.pk)])
        self.assertEqual(result["tareas_total"], 5)
        self.assertEqual(result["tareas_sin_fecha"], 1)

    def test_privacidad_lector_y_revocacion(self):
        self.tarea(fecha_objetivo=self.today)
        CultivoMiembro.objects.create(cultivo=self.c, usuario=self.reader, rol="lector")
        result = resumen_hoy(self.reader, ahora=self.now)
        self.assertEqual(result["atencion_total"], 1)
        self.assertFalse(result["puede_registrar"])
        self.assertFalse(result["activos"][0]["puede_editar"])
        self.client.force_login(self.reader)
        page = self.client.get("/")
        self.assertContains(page, "Solo lectura")
        self.assertNotContains(page, f'/registrar/?cultivo={self.c.pk}')
        CultivoMiembro.objects.all().delete()
        result = resumen_hoy(self.reader, ahora=self.now)
        self.assertEqual(result["activos"], [])
        self.assertEqual(result["atencion_total"], 0)

    def test_cierre_y_archivo_excluyen_pendientes_diarios(self):
        self.tarea(fecha_objetivo=self.today)
        for changes, key in [({"estado": "finalizado"}, "finalizados"), ({"archivado": True}, "archivados")]:
            Cultivo.objects.filter(pk=self.c.pk).update(**changes)
            result = resumen_hoy(self.user, ahora=self.now)
            self.assertEqual(result["activos"], [])
            self.assertEqual(result["atencion_total"], 0)
            self.assertEqual(len(result[key]), 1)

    def test_frescura_fecha_local_y_desempate_de_mediciones(self):
        with timezone.override("America/Argentina/Buenos_Aires"):
            self.medir(timestamp=self.now - timedelta(days=1))
            self.assertEqual(resumen_hoy(self.user, ahora=self.now)["activos"][0]["frescura"], "anterior")
            self.medir(timestamp=self.now)
            latest = self.medir(timestamp=self.now)
            result = resumen_hoy(self.user, ahora=self.now)
            self.assertEqual(result["activos"][0]["ultima_medicion"].pk, latest.pk)
            self.assertEqual(result["sin_medicion_hoy"], 0)
            # A las 01 UTC todavía es el día anterior en Buenos Aires.
            self.assertEqual(resumen_hoy(self.user, ahora=self.now.replace(hour=1))["activos"][0]["frescura"], "futura")

    def test_sin_datos_no_inventa_una_medicion(self):
        result = resumen_hoy(self.user, ahora=self.now)
        self.assertIsNone(result["activos"][0]["ultima_medicion"])
        self.assertEqual(result["sin_medicion_hoy"], 1)
        self.client.force_login(self.user)
        self.assertContains(self.client.get("/"), "Sin mediciones de ambiente")

    def test_cantidad_consultas_no_crece_por_cultivo(self):
        self.medir(timestamp=self.now)
        self.tarea(fecha_objetivo=self.today)
        with CaptureQueriesContext(connection) as initial:
            resumen_hoy(self.user, ahora=self.now)
        for i in range(8):
            c = Cultivo.objects.create(nombre=f"Otro {i}", fecha_inicio=self.today, propietario=self.user)
            self.medir(cultivo=c, timestamp=self.now)
            Tarea.objects.create(cultivo=c, titulo="Revisión", fecha_objetivo=self.today)
        with CaptureQueriesContext(connection) as expanded:
            result = resumen_hoy(self.user, ahora=self.now)
        self.assertEqual(len(result["activos"]), 9)
        self.assertEqual(len(initial), len(expanded))
        # Las consultas no crecen con la cantidad de cultivos (etapas y rangos se leen una vez).
        self.assertLessEqual(len(expanded), 11)

    def test_lista_acotada_mantiene_conteo_y_orden(self):
        for i in range(17):
            self.tarea(fecha_objetivo=self.today - timedelta(days=i))
        result = resumen_hoy(self.user, ahora=self.now)
        self.assertEqual(result["atencion_total"], 17)
        self.assertEqual(result["atencion_restante"], 5)
        self.assertEqual(len(result["atencion"]), 12)
        self.assertEqual(result["atencion"][0]["fecha"], self.today - timedelta(days=16))

    def test_inicio_requiere_sesion(self):
        self.assertEqual(self.client.get("/").status_code, 302)


class HoyRediseñoTests(TestCase):
    def setUp(self):
        from .services.etapas import cambiar_etapa
        self.user = User.objects.create_user(username="hoy-nuevo")
        hoy = timezone.localdate()
        self.c = Cultivo.objects.create(nombre="Carpa", fecha_inicio=hoy - timedelta(days=20), propietario=self.user)
        cambiar_etapa(self.c, "veg_temprano", self.c.fecha_inicio)
        ParametroIdeal.objects.update_or_create(etapa="veg_temprano", defaults=dict(
            temp_min=22, temp_max=28, hr_min=55, hr_max=70, ph_min=6, ph_max=7, vpd_min="0.8", vpd_max="1.0"))
        self.client.force_login(self.user)

    def test_alerta_de_vpd_reciente_y_no_vieja(self):
        # 27° y 45% dan VPD 1,96: alto para veg temprano.
        MedicionAmbiente.objects.create(cultivo=self.c, temperatura_c=27, humedad_relativa=45,
                                        timestamp=timezone.now() - timedelta(minutes=10))
        result = resumen_hoy(self.user)
        self.assertEqual([a["estado"] for a in result["alertas"]], ["alto"])
        self.assertEqual(result["atencion_total"], 1)
        self.assertContains(self.client.get("/"), "ver aire")
        MedicionAmbiente.objects.update(timestamp=timezone.now() - timedelta(days=2))
        result = resumen_hoy(self.user)
        self.assertEqual(result["alertas"], [])
        self.assertTrue(result["activos"][0]["dato_viejo"])

    def test_dia_etapa_y_dias_sin_riego(self):
        Riego.objects.create(cultivo=self.c, volumen_total_ml=500, timestamp=timezone.now() - timedelta(days=4))
        item = resumen_hoy(self.user)["activos"][0]
        self.assertEqual((item["etapa"], item["dia"], item["en_flora"], item["dias_sin_riego"]), ("veg_temprano", 20, False, 4))
        self.assertContains(self.client.get("/"), "sin riego 4 d")

    def test_completar_y_deshacer_desde_hoy(self):
        from django.urls import reverse
        tarea = Tarea.objects.create(cultivo=self.c, titulo="Podar", fecha_objetivo=timezone.localdate())
        self.assertContains(self.client.get("/"), f'id="hoy-tarea-{tarea.pk}"')
        hecha = self.client.post(reverse("growlog:tarea_completar", args=[tarea.pk]), {"origen": "hoy"}, HTTP_HX_REQUEST="true")
        self.assertContains(hecha, "Deshacer")
        tarea.refresh_from_db()
        self.assertTrue(tarea.completada)
        vuelta = self.client.post(reverse("growlog:tarea_descompletar", args=[tarea.pk]), {"origen": "hoy"}, HTTP_HX_REQUEST="true")
        self.assertContains(vuelta, "Marcar como hecha: Podar")
        tarea.refresh_from_db()
        self.assertFalse(tarea.completada)
