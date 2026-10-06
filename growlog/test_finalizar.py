"""Un cultivo finalizado deja de contar días y se puede reabrir."""
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CambioFotoperiodo, Cultivo, CultivoMiembro, Planta, Riego
from .services.etapas import cambiar_etapa
from .services.riegos import guardar_riego


class CultivoFinalizadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.duenio = User.objects.create_user("duenio")
        cls.lector = User.objects.create_user("lector")

    def setUp(self):
        hoy = timezone.localdate()
        self.cultivo = Cultivo.objects.create(
            nombre="Cerrado", fecha_inicio=hoy - timedelta(days=99), creado_por=self.duenio,
        )
        CultivoMiembro.objects.create(cultivo=self.cultivo, usuario=self.lector, rol="lector")
        cambiar_etapa(self.cultivo, "veg_temprano", self.cultivo.fecha_inicio)
        # Flip el día 31, cierre el día 80: veinte días antes de hoy.
        cambiar_etapa(self.cultivo, "flora_temprana", self.cultivo.fecha_inicio + timedelta(days=30))
        CambioFotoperiodo.objects.create(
            cultivo=self.cultivo, fotoperiodo="12/12", hora_lights_on=time(8, 0),
            fecha_inicio=self.cultivo.fecha_inicio + timedelta(days=30),
        )
        planta = Planta.objects.create(cultivo=self.cultivo, apodo="P1")
        guardar_riego(riego=Riego(cultivo=self.cultivo, timestamp=timezone.now() - timedelta(days=21)),
                      detalles=[{"planta": planta, "volumen_ml": 500}])
        self.cultivo.refresh_from_db()
        self.cultivo.estado = "finalizado"
        self.cultivo.fecha_fin = self.cultivo.fecha_inicio + timedelta(days=79)
        self.cultivo.save()
        self.detalle = reverse("growlog:cultivo_detail", args=[self.cultivo.slug])
        self.reabrir = reverse("growlog:cultivo_reabrir", args=[self.cultivo.slug])

    def test_contadores_se_detienen_en_el_cierre(self):
        self.assertEqual(self.cultivo.dias_desde_inicio, 80)
        self.assertEqual(self.cultivo.dia_flora, 50)

    def test_cultivo_abierto_sigue_contando_hasta_hoy(self):
        self.cultivo.fecha_fin = None
        self.assertEqual(self.cultivo.dias_desde_inicio, 100)
        self.assertEqual(self.cultivo.dia_flora, 70)

    def test_detalle_muestra_el_cierre_y_no_datos_en_vivo(self):
        self.client.force_login(self.duenio)
        respuesta = self.client.get(self.detalle)
        self.assertEqual(respuesta.context["dia_flora"], 50)
        self.assertIsNone(respuesta.context["luz_estado_actual"])
        self.assertIsNone(respuesta.context["dias_sin_riego"])
        self.assertContains(respuesta, "cultivo finalizado el")
        self.assertNotContains(respuesta, "cultivo activo")
        self.assertContains(respuesta, self.reabrir)
        self.assertNotContains(respuesta, reverse("growlog:cultivo_finalizar", args=[self.cultivo.slug]))

    def test_reabrir_recupera_la_etapa_y_quita_el_cierre(self):
        self.client.force_login(self.duenio)
        respuesta = self.client.post(self.reabrir)
        self.assertRedirects(respuesta, self.detalle)
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado, "floracion")
        self.assertIsNone(self.cultivo.fecha_fin)
        self.assertEqual(self.cultivo.dias_desde_inicio, 100)

    def test_reabrir_sin_historial_de_etapas_queda_en_vegetativo(self):
        self.cultivo.cambios_etapa.all().delete()
        self.client.force_login(self.duenio)
        self.client.post(self.reabrir)
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado, "vegetativo")

    def test_reabrir_por_get_no_cambia_nada(self):
        self.client.force_login(self.duenio)
        self.client.get(self.reabrir)
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado, "finalizado")

    def test_lector_no_puede_reabrir_ni_ve_el_boton(self):
        self.client.force_login(self.lector)
        self.assertNotContains(self.client.get(self.detalle), self.reabrir)
        self.assertEqual(self.client.post(self.reabrir).status_code, 403)
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado, "finalizado")
