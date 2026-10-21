"""Escrituras de la API v1: validan igual que web/Registrar y cubren cada endpoint."""

import hashlib
import json

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from .models import APIToken, Cultivo, MedicionPlanta, Nutriente, NutrienteAplicado, Planta, Riego, RiegoPlanta


class ApiEscriturasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("dueno")
        cls.cultivo = Cultivo.objects.create(
            nombre="Carpa API", fecha_inicio=timezone.localdate(), creado_por=cls.user, propietario=cls.user,
        )
        cls.p1 = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")
        cls.p2 = Planta.objects.create(cultivo=cls.cultivo, apodo="P2")
        cls.archivada = Planta.objects.create(cultivo=cls.cultivo, apodo="Vieja", archivado=True)
        cls.nutriente = Nutriente.objects.create(nombre="Grow")
        APIToken.objects.create(user=cls.user, token_hash=hashlib.sha256(b"token-escrituras").hexdigest())

    def setUp(self):
        cache.clear()
        self.base = f"/api/v1/cultivos/{self.cultivo.slug}"

    def api(self, method, url, body=None):
        if method == "get":
            return self.client.get(url, HTTP_AUTHORIZATION="Bearer token-escrituras")
        return getattr(self.client, method)(
            url, data=json.dumps(body or {}), content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token-escrituras",
        )

    def crear_riego(self):
        response = self.api("post", f"{self.base}/riegos/", {
            "ph_agua": 6.2, "detalle_plantas": [{"planta_uuid": str(self.p1.uuid), "volumen_ml": 500}],
            "nutrientes": [{"nutriente_id": self.nutriente.pk, "dosis_g_por_litro": 1.5}],
        })
        self.assertEqual(response.status_code, 201, response.content)
        return Riego.objects.get(pk=response.json()["data"]["id"])

    def test_nutriente_con_dosis_no_positiva_se_rechaza(self):
        riego = self.crear_riego()
        for dosis in (-5, 0, "abc"):
            with self.subTest(dosis=dosis):
                response = self.api("post", f"{self.base}/riegos/{riego.pk}/nutrientes/",
                                    {"nutriente_id": self.nutriente.pk, "dosis_g_por_litro": dosis})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(NutrienteAplicado.objects.filter(riego=riego).count(), 1)

    def test_runoff_por_planta_valida_rango_y_mantiene_total(self):
        riego = self.crear_riego()
        url = f"{self.base}/riegos/{riego.pk}/plantas/"
        self.assertEqual(self.api("post", url, {"planta_uuid": str(self.p2.uuid), "volumen_ml": 300, "ph_runoff": 99}).status_code, 400)
        response = self.api("post", url, {"planta_uuid": str(self.p2.uuid), "volumen_ml": 300, "ph_runoff": 6.5})
        self.assertEqual(response.status_code, 201, response.content)
        riego.refresh_from_db()
        self.assertEqual(riego.volumen_total_ml, 800)

        rp_url = f"{url}{response.json()['data']['id']}/"
        self.assertEqual(self.api("patch", rp_url, {"ec_runoff": -3}).status_code, 400)
        self.assertEqual(self.api("patch", rp_url, {"volumen_ml": 200}).status_code, 200)
        riego.refresh_from_db()
        self.assertEqual(riego.volumen_total_ml, 700)

        self.assertEqual(self.api("delete", rp_url).status_code, 200)
        riego.refresh_from_db()
        self.assertEqual(riego.volumen_total_ml, 500)
        unica = RiegoPlanta.objects.get(riego=riego)
        self.assertEqual(self.api("delete", f"{url}{unica.pk}/").status_code, 400)

    def test_nudos_count_invalido_da_400(self):
        url = f"/api/v1/plantas/{self.p1.uuid}/mediciones/"
        for nudos in ("abc", -4, True):
            with self.subTest(nudos=nudos):
                self.assertEqual(self.api("post", url, {"nudos_count": nudos}).status_code, 400)
        self.assertFalse(MedicionPlanta.objects.exists())
        response = self.api("post", url, {"nudos_count": 6})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["fecha"], timezone.localdate().isoformat())

    def test_evento_no_acepta_plantas_archivadas(self):
        body = {"tipo": "otro", "descripcion": "x", "plantas_afectadas": [str(self.archivada.uuid)]}
        response = self.api("post", f"{self.base}/eventos/", body)
        self.assertEqual(response.status_code, 400)
        self.assertIn("archivado", response.json()["error"])

    def test_crud_basico_de_cada_recurso(self):
        hoy = timezone.localdate().isoformat()
        casos = [
            (f"{self.base}/mediciones/", {"temperatura_c": 25, "humedad_relativa": 60}, {"humedad_relativa": 55}),
            (f"{self.base}/mediciones-ec/", {"ph": 6.1, "ec": 1.2}, {"tipo": "runoff"}),
            (f"{self.base}/eventos/", {"tipo": "otro", "descripcion": "Poda", "plantas_afectadas": [str(self.p1.uuid)]},
             {"follow_up_resuelto": "true"}),
            (f"{self.base}/tareas/", {"titulo": "Regar"}, {"completada": True}),
            (f"{self.base}/cambios-fotoperiodo/", {"fotoperiodo": "18/6", "hora_lights_on": "08:00", "fecha_inicio": hoy},
             {"notas": "ok"}),
            (f"{self.base}/plantas/", {"apodo": "P3", "thc_estimado": 20}, {"strain": "Gummy"}),
            (f"{self.base}/lecturas-medidor/", {"fecha": hoy, "kwh_real": 15}, {"kwh_real": 20}),
            ("/api/v1/tarifas/", {"fecha_desde": hoy, "precio_kwh": 100}, {"distribuidora": "Edenor"}),
            ("/api/v1/equipos/", {"nombre": "LED", "categoria": "lampara", "watts": 200, "horas_dia": 18}, {"activo": False}),
        ]
        for url, alta, cambio in casos:
            with self.subTest(url=url):
                response = self.api("post", url, alta)
                self.assertEqual(response.status_code, 201, response.content)
                data = response.json()["data"]
                detalle = f"/api/v1/plantas/{data['uuid']}/" if "uuid" in data else f"{url}{data['id']}/"
                self.assertEqual(self.api("patch", detalle, cambio).status_code, 200)
                self.assertEqual(self.api("get", detalle).status_code, 200)
                self.assertEqual(self.api("delete", detalle).status_code, 200)

    def test_errores_de_entrada_son_400_y_no_500(self):
        casos = [
            (f"{self.base}/mediciones/", {"temperatura_c": 90, "humedad_relativa": 60}),
            (f"{self.base}/mediciones/", {"temperatura_c": "x", "humedad_relativa": 60}),
            (f"{self.base}/cambios-fotoperiodo/", {"fotoperiodo": "20/6", "hora_lights_on": "08:00", "fecha_inicio": "2026-01-01"}),
            (f"{self.base}/tareas/", {"titulo": "x", "prioridad": ["alta"]}),
            (f"{self.base}/canopy/", {"scrog_cells": ["x"]}),
            (f"{self.base}/canopy/", {"colas": [1]}),
            ("/api/v1/equipos/", {"nombre": "LED", "categoria": "lampara", "watts": 200, "horas_dia": 30}),
        ]
        for url, body in casos:
            with self.subTest(url=url, body=body):
                self.assertEqual(self.api("post", url, body).status_code, 400)

    def test_patch_no_permite_vaciar_campos_obligatorios(self):
        response = self.api("post", f"{self.base}/mediciones/", {"temperatura_c": 25, "humedad_relativa": 60})
        url = f"{self.base}/mediciones/{response.json()['data']['id']}/"
        self.assertEqual(self.api("patch", url, {"temperatura_c": None}).status_code, 400)
