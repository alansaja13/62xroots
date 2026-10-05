"""Regresiones del recorrido de bugs de septiembre 2026."""
import hashlib
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import (
    APIToken, CambioEtapaCultivo, CambioEtapaPlanta, CanopySnapshot, Cultivo, CultivoMiembro, MedicionAmbiente, MedicionPlanta,
    ParametroIdeal, Planta, Riego, Tarea,
)
from .views.auth import _get_client_ip


class BugfixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("duena")
        hoy = timezone.localdate()
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=hoy - timedelta(days=60), creado_por=cls.owner)
        cls.planta = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")
        cls.raw_token = "token-bugfixes"
        APIToken.objects.create(user=cls.owner, token_hash=hashlib.sha256(cls.raw_token.encode()).hexdigest())

    def setUp(self):
        cache.clear()
        self.client.force_login(self.owner)

    def api(self, method, url, body):
        return getattr(self.client, method)(url, data=json.dumps(body), content_type="application/json",
                                            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}")

    # 1 · Borrar una planta con historial la archiva, sin cascada.
    def test_eliminar_planta_con_historial_la_archiva_y_conserva_datos(self):
        cambio = CambioEtapaPlanta.objects.create(planta=self.planta, etapa="veg_temprano", fecha_inicio=self.cultivo.fecha_inicio)
        response = self.client.post(reverse("growlog:planta_eliminar", args=[self.planta.pk]))
        self.assertEqual(response.status_code, 302)
        self.planta.refresh_from_db()
        self.assertTrue(self.planta.archivado)
        self.assertTrue(CambioEtapaPlanta.objects.filter(pk=cambio.pk).exists())

    def test_eliminar_planta_sin_historial_la_borra(self):
        nueva = Planta.objects.create(cultivo=self.cultivo, apodo="Vacía")
        self.client.post(reverse("growlog:planta_eliminar", args=[nueva.pk]))
        self.assertFalse(Planta.objects.filter(pk=nueva.pk).exists())

    def test_api_delete_planta_con_historial_archiva(self):
        CambioEtapaPlanta.objects.create(planta=self.planta, etapa="veg_temprano", fecha_inicio=self.cultivo.fecha_inicio)
        response = self.api("delete", f"/api/v1/plantas/{self.planta.uuid}/", {})
        self.assertEqual(response.json()["data"], {"archived": str(self.planta.uuid)})
        self.assertTrue(Planta.objects.get(pk=self.planta.pk).archivado)

    # 2 · El bloqueo de login usa la IP que agregó el proxy, no la que manda el cliente.
    def test_ip_del_cliente_es_la_que_agrego_el_proxy(self):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 9.9.9.9", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(_get_client_ip(request), "9.9.9.9")

    def test_cambiar_x_forwarded_for_no_saltea_el_bloqueo(self):
        self.client.logout()
        for intento in range(10):
            self.client.post("/login/", {"username": "duena", "password": "mal"},
                             HTTP_X_FORWARDED_FOR=f"{intento}.0.0.1, 5.5.5.5")
        response = self.client.post("/login/", {"username": "duena", "password": "mal"},
                                    HTTP_X_FORWARDED_FOR="77.0.0.1, 5.5.5.5")
        self.assertContains(response, "Demasiados intentos fallidos")

    # 3 · El timeline no hace una consulta por fila.
    def test_timeline_consultas_acotadas(self):
        for dia in range(20):
            MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=60,
                                            timestamp=timezone.now() - timedelta(days=dia), creado_por=self.owner)
        for _ in range(5):
            Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=500, creado_por=self.owner)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(reverse("growlog:timeline", args=[self.cultivo.slug])).status_code, 200)
        self.assertLess(len(queries), 30)

    # 4 · El VPD de una medición se evalúa con la etapa vigente cuando se midió.
    def test_vpd_historico_usa_la_etapa_de_su_fecha(self):
        base = dict(temp_min=20, temp_max=28, hr_min=40, hr_max=70, ph_min=6, ph_max=7)
        ParametroIdeal.objects.update_or_create(etapa="veg_temprano", defaults={"vpd_min": "0.80", "vpd_max": "1.20", **base})
        ParametroIdeal.objects.update_or_create(etapa="flora_temprana", defaults={"vpd_min": "1.20", "vpd_max": "1.60", **base})
        hoy = timezone.localdate()
        CambioEtapaCultivo.objects.create(cultivo=self.cultivo, etapa="veg_temprano", fecha_inicio=hoy - timedelta(days=60))
        CambioEtapaCultivo.objects.create(cultivo=self.cultivo, etapa="flora_temprana", fecha_inicio=hoy - timedelta(days=10))
        vieja = MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=68,
                                                timestamp=timezone.now() - timedelta(days=30))
        self.assertAlmostEqual(vieja.vpd, 1.0, places=1)
        self.assertEqual(vieja.vpd_estado, "ideal")  # con los rangos de flora de hoy sería "bajo"

    # 5 · "Planta activa" excluye archivadas y cosechadas en conteos y en Registrar.
    def test_plantas_archivadas_o_cosechadas_no_cuentan_como_activas(self):
        Planta.objects.create(cultivo=self.cultivo, apodo="Archivada", archivado=True)
        Planta.objects.create(cultivo=self.cultivo, apodo="Cosechada", estado="cosechada")
        self.assertEqual(list(self.cultivo.plantas.activas()), [self.planta])
        contexto = self.client.get(reverse("growlog:registro_contexto")).json()
        self.assertEqual([p["nombre"] for p in contexto["cultivos"][0]["plantas"]], ["P1"])
        hoy = self.client.get(reverse("growlog:dashboard")).context["activos"][0]
        self.assertEqual(hoy["plantas_count"], 1)

    # 6 y 12 · La API responde 400, no 500, y no confunde "false" con verdadero.
    def test_api_fechas_no_string_y_uuid_invalido_dan_400(self):
        response = self.api("post", f"/api/v1/cultivos/{self.cultivo.slug}/tareas/", {"titulo": "x", "fecha_objetivo": 5})
        self.assertEqual(response.status_code, 400)
        riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=500)
        response = self.api("post", f"/api/v1/cultivos/{self.cultivo.slug}/riegos/{riego.pk}/plantas/",
                            {"planta_uuid": "no-es-uuid", "volumen_ml": 100})
        self.assertEqual(response.status_code, 400)

    def test_api_booleans_se_interpretan(self):
        url = f"/api/v1/plantas/{self.planta.uuid}/"
        self.assertEqual(self.api("patch", url, {"archivado": "false"}).status_code, 200)
        self.assertFalse(Planta.objects.get(pk=self.planta.pk).archivado)
        response = self.api("patch", url, {"archivado": "quizás"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("archivado", response.json()["error"])

    # 7 · Guardar canopy valida todo antes de crear y no deja snapshots huérfanos.
    def test_canopy_rechaza_entradas_invalidas_sin_crear_snapshot(self):
        url = reverse("growlog:canopy_guardar", args=[self.cultivo.slug])
        cola = {"planta_uuid": str(self.planta.uuid), "indice": 0, "x": 0.5, "y": 0.5}
        for body in ([], {"colas": [1]}, {"scrog_cells": ["x"]}, {"colas": [cola, cola]},
                     {"colas": [{**cola, "indice": -1}]}):
            with self.subTest(body=body):
                response = self.client.post(url, data=json.dumps(body), content_type="application/json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(CanopySnapshot.objects.exists())
        response = self.client.post(url, data=json.dumps({"colas": [cola], "scrog_cells": [1, 1, 2]}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["scrog_cells"], [1, 2])

    # 8 · Borrar o reemplazar la foto de una medición borra el archivo.
    def test_fotos_se_borran_del_storage(self):
        medicion = MedicionPlanta.objects.create(planta=self.planta, foto=SimpleUploadedFile("a.jpg", b"img-a"))
        storage, primera = medicion.foto.storage, medicion.foto.name
        with self.captureOnCommitCallbacks(execute=True):
            medicion.foto = SimpleUploadedFile("b.jpg", b"img-b")
            medicion.save()
        self.assertFalse(storage.exists(primera))
        segunda = medicion.foto.name
        with self.captureOnCommitCallbacks(execute=True):
            medicion.delete()
        self.assertFalse(storage.exists(segunda))

    # 9, 10 y 13 · Casos borde que daban 500 o números sin sentido.
    def test_nombre_sin_letras_tiene_slug_y_hoy_carga(self):
        cultivo = Cultivo.objects.create(nombre="🌱🌱", fecha_inicio=timezone.localdate(), creado_por=self.owner)
        self.assertEqual(cultivo.slug, "cultivo")
        self.assertEqual(self.client.get(reverse("growlog:dashboard")).status_code, 200)

    def test_tendencias_con_dias_enorme_no_rompe(self):
        url = reverse("growlog:cultivo_tendencias_json", args=[self.cultivo.slug])
        self.assertEqual(self.client.get(url, {"dias": "999999999999"}).status_code, 200)

    def test_cultivo_que_no_empezo_esta_en_dia_cero(self):
        futuro = Cultivo(nombre="Futuro", fecha_inicio=timezone.localdate() + timedelta(days=3))
        self.assertEqual(futuro.dias_desde_inicio, 0)
