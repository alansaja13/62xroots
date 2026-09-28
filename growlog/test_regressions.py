"""Regresiones de integridad y registro detectadas en la revisión de producto."""

import hashlib
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .models import (
    APIToken, Cultivo, CultivoMiembro, Evento, LecturaMedidor, MedicionAmbiente, MedicionEC,
    Nutriente, NutrienteAplicado, Planta, Riego, RiegoPlanta, Tarea,
)
from .services.riegos import guardar_riego


class BitacoraRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user("editor", is_staff=True)
        cls.lector = User.objects.create_user("lector")
        cls.cultivo = Cultivo.objects.create(
            nombre="Bitácora de prueba", fecha_inicio=timezone.localdate(), creado_por=cls.editor,
        )
        CultivoMiembro.objects.create(cultivo=cls.cultivo, usuario=cls.lector, rol="lector")
        cls.planta = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")
        cls.raw_token = "token-exclusivo-de-la-suite-local"
        APIToken.objects.create(
            user=cls.editor, token_hash=hashlib.sha256(cls.raw_token.encode()).hexdigest(),
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.editor)

    def api_post(self, resource, body):
        return self.client.post(
            f"/api/v1/cultivos/{self.cultivo.slug}/{resource}/",
            data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )

    def test_lector_no_puede_crear_lectura_por_post_directo(self):
        self.client.force_login(self.lector)
        response = self.client.post(reverse("growlog:energia", args=[self.cultivo.slug]), {
            "fecha": timezone.localdate().isoformat(), "kwh_real": "15",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LecturaMedidor.objects.exists())

    def test_usuario_inactivo_no_puede_usar_token_existente(self):
        self.editor.is_active = False
        self.editor.save(update_fields=["is_active"])
        response = self.client.get(
            "/api/v1/cultivos/", HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        self.assertEqual(response.status_code, 401)

    def test_api_rechaza_json_que_no_es_objeto(self):
        for body in ([], None, True, "texto", 1):
            with self.subTest(body=body):
                response = self.api_post("mediciones", body)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])
        self.assertFalse(MedicionAmbiente.objects.exists())

    def test_riego_duplicado_no_deja_cabecera_huerfana(self):
        detalle = {"planta_uuid": str(self.planta.uuid), "volumen_ml": 500}
        response = self.api_post("riegos", {"detalle_plantas": [detalle, detalle]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Riego.objects.exists())
        self.assertFalse(RiegoPlanta.objects.exists())

    def test_riego_rechaza_filas_malformadas(self):
        for detalle in (None, [], "planta"):
            with self.subTest(detalle=detalle):
                response = self.api_post("riegos", {"detalle_plantas": [detalle]})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Riego.objects.exists())

    def test_riego_rechaza_runoff_fuera_de_rango(self):
        response = self.api_post("riegos", {"detalle_plantas": [{
            "planta_uuid": str(self.planta.uuid), "volumen_ml": 500, "ph_runoff": 20,
        }]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Riego.objects.exists())

    def test_riego_api_guarda_total_detalles_y_nutrientes(self):
        otra = Planta.objects.create(cultivo=self.cultivo, apodo="P2")
        nutriente = Nutriente.objects.create(nombre="Producto de prueba")
        response = self.api_post("riegos", {
            "detalle_plantas": [
                {"planta_uuid": str(self.planta.uuid), "volumen_ml": 500},
                {"planta_uuid": str(otra.uuid), "volumen_ml": 700},
            ],
            "nutrientes": [{"nutriente_id": nutriente.pk, "dosis_g_por_litro": "1.25"}],
        })
        self.assertEqual(response.status_code, 201, response.content)
        riego = Riego.objects.get()
        self.assertEqual(riego.volumen_total_ml, 1200)
        self.assertEqual(riego.detalle_plantas.count(), 2)
        self.assertEqual(riego.nutrientes_aplicados.get().dosis_g_por_litro, Decimal("1.25"))

    def test_fallo_de_persistencia_revierte_todo_el_riego(self):
        riego = Riego(cultivo=self.cultivo, creado_por=self.editor)
        with patch.object(RiegoPlanta.objects, "update_or_create", side_effect=IntegrityError("fallo simulado")):
            with self.assertRaises(IntegrityError):
                guardar_riego(riego=riego, detalles=[{"planta": self.planta, "volumen_ml": 500}])
        self.assertFalse(Riego.objects.exists())
        self.assertFalse(RiegoPlanta.objects.exists())

    def test_fallo_editando_conserva_detalles_y_total_anterior(self):
        riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=500)
        detalle = RiegoPlanta.objects.create(riego=riego, planta=self.planta, volumen_ml=500)
        with patch.object(RiegoPlanta.objects, "update_or_create", side_effect=IntegrityError("fallo simulado")):
            with self.assertRaises(IntegrityError):
                guardar_riego(riego=riego, detalles=[{"planta": self.planta, "volumen_ml": 900}])
        riego.refresh_from_db()
        detalle.refresh_from_db()
        self.assertEqual(riego.volumen_total_ml, 500)
        self.assertEqual(detalle.volumen_ml, 500)

    def test_servicio_rechaza_planta_de_otro_cultivo(self):
        otro = Cultivo.objects.create(nombre="Otro", fecha_inicio=timezone.localdate())
        with self.assertRaises(ValidationError):
            guardar_riego(
                riego=Riego(cultivo=otro), detalles=[{"planta": self.planta, "volumen_ml": 500}],
            )
        self.assertFalse(Riego.objects.exists())

    def test_editar_riego_conserva_planta_archivada_y_nutrientes(self):
        riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=500)
        RiegoPlanta.objects.create(riego=riego, planta=self.planta, volumen_ml=500)
        nutriente = Nutriente.objects.create(nombre="Producto")
        NutrienteAplicado.objects.create(riego=riego, nutriente=nutriente, dosis_g_por_litro=1)
        self.planta.archivado = True
        self.planta.save(update_fields=["archivado"])
        url = reverse("growlog:riego_editar", args=[riego.pk])
        self.assertContains(self.client.get(url), "archivada")
        response = self.client.post(url, {
            "timestamp": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "notas": "Observación corregida",
            "rp-TOTAL_FORMS": "1", "rp-INITIAL_FORMS": "1",
            "rp-0-planta_id": str(self.planta.pk), "rp-0-incluida": "on", "rp-0-volumen_ml": "500",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(riego.detalle_plantas.get().volumen_ml, 500)
        self.assertEqual(riego.nutrientes_aplicados.count(), 1)
        riego.refresh_from_db()
        self.assertEqual(riego.notas, "Observación corregida")

    def test_carga_rapida_vieja_redirige_a_registrar(self):
        # Registrar es la única pantalla de carga; los marcadores viejos siguen andando.
        response = self.client.get(f"/cultivo/{self.cultivo.slug}/quick/")
        self.assertRedirects(response, f"{reverse('growlog:registrar')}?cultivo={self.cultivo.pk}", fetch_redirect_response=False)

    def test_pantallas_clasicas_de_alta_ya_no_existen(self):
        # El alta de riego/evento/EC/tarea vive solo en Registrar; estas rutas se dieron de baja.
        for name in ("tarea_crear", "evento_crear", "riego_crear", "medicion_ec_crear", "tarea_rapida"):
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(f"growlog:{name}", args=[self.cultivo.slug])
