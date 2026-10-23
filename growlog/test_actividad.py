"""Ingresos y panel de actividad."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cultivo, Ingreso, MedicionAmbiente, Riego
from .services.actividad import resumen_actividad
from .signals import dispositivo_corto

IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
EDGE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36 Edg/120.0")


class IngresosTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("amigo", password="clave-segura-123")

    def test_dispositivo_corto(self):
        self.assertEqual(dispositivo_corto(IPHONE), "iPhone · Safari")
        self.assertEqual(dispositivo_corto(EDGE), "Windows · Edge")
        self.assertEqual(dispositivo_corto(""), "")

    def test_ingreso_ok_y_fallido_quedan_registrados(self):
        url = reverse("growlog:login")
        self.client.post(url, {"username": "amigo", "password": "mal"}, HTTP_USER_AGENT=IPHONE)
        self.client.post(url, {"username": "amigo", "password": "clave-segura-123"}, HTTP_USER_AGENT=IPHONE)
        fallido, ok = Ingreso.objects.order_by("pk")
        self.assertFalse(fallido.exito)
        self.assertIsNone(fallido.usuario)
        self.assertEqual(fallido.nombre_usado, "amigo")
        self.assertTrue(ok.exito)
        self.assertEqual(ok.usuario, self.user)
        self.assertEqual(ok.dispositivo, "iPhone · Safari")

    def test_los_ingresos_viejos_se_borran_solos(self):
        viejo = Ingreso.objects.create(usuario=self.user, nombre_usado="amigo")
        Ingreso.objects.filter(pk=viejo.pk).update(creado_en=timezone.now() - timedelta(days=91))
        self.client.force_login(self.user)
        self.assertFalse(Ingreso.objects.filter(pk=viejo.pk).exists())
        self.assertEqual(Ingreso.objects.count(), 1)


class PanelActividadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin", password="x")
        cls.amigo = User.objects.create_user("amigo")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate(), propietario=cls.amigo)

    def test_solo_superusuarios(self):
        self.client.force_login(self.amigo)
        self.assertEqual(self.client.get(reverse("growlog:actividad")).status_code, 404)
        self.assertNotContains(self.client.get("/"), reverse("growlog:actividad"))
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("growlog:actividad")), "Por persona")

    def test_cuenta_registros_por_persona_y_arma_movimientos(self):
        ahora = timezone.now()
        MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=24, humedad_relativa=60,
                                        luz_estado="on", creado_por=self.amigo, timestamp=ahora - timedelta(days=2))
        Riego.objects.create(cultivo=self.cultivo, creado_por=self.amigo, volumen_total_ml=500,
                             timestamp=ahora - timedelta(days=20))
        resumen = resumen_actividad(ahora=ahora)
        amigo = next(p for p in resumen["personas"] if p["usuario"] == self.amigo)
        self.assertEqual((amigo["registros_7"], amigo["registros_30"]), (1, 2))
        self.assertTrue(amigo["activo_7"])
        self.assertEqual([m["texto"] for m in resumen["movimientos"]], ["midió el ambiente", "registró un riego"])
