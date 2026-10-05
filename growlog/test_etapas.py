"""Etapa única del cultivo: estado, día de flora y VPD salen del mismo historial."""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CambioEtapaCultivo, CambioEtapaPlanta, Cultivo, MedicionAmbiente, ParametroIdeal, Planta
from .services.etapas import cambiar_etapa
from .utils import etapa_efectiva_cultivo, etapa_efectiva_planta

BASE = dict(temp_min=20, temp_max=28, hr_min=40, hr_max=70, ph_min=6, ph_max=7)


def parametro(etapa, vpd_min, vpd_max):
    ParametroIdeal.objects.update_or_create(etapa=etapa, defaults={"vpd_min": vpd_min, "vpd_max": vpd_max, **BASE})


class EtapaCultivoTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.user = User.objects.create_user("duena")
        self.cultivo = Cultivo.objects.create(
            nombre="Carpa", fecha_inicio=self.hoy - timedelta(days=60), creado_por=self.user)
        self.planta = Planta.objects.create(cultivo=self.cultivo, apodo="P1")
        self.client.force_login(self.user)

    def dia(self, dias_atras):
        return self.hoy - timedelta(days=dias_atras)

    def test_pasar_de_flora_temprana_a_tardia_no_reinicia_el_contador(self):
        cambiar_etapa(self.cultivo, "veg_tardio", self.dia(40))
        cambiar_etapa(self.cultivo, "flora_temprana", self.dia(20))
        cambiar_etapa(self.cultivo, "flora_tardia", self.dia(2))
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.fecha_inicio_flora, self.dia(20))
        self.assertEqual(self.cultivo.dia_flora, 21)
        self.assertEqual(self.cultivo.estado, "floracion")

    def test_marcar_flora_no_pisa_una_fecha_ya_marcada(self):
        cambiar_etapa(self.cultivo, "flora_temprana", self.dia(15))
        self.client.post(reverse("growlog:cultivo_marcar_flora", args=[self.cultivo.slug]))
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.fecha_inicio_flora, self.dia(15))

    def test_marcar_flora_la_primera_vez_pasa_a_flora_hoy(self):
        cambiar_etapa(self.cultivo, "veg_tardio", self.dia(30))
        self.client.post(reverse("growlog:cultivo_marcar_flora", args=[self.cultivo.slug]))
        self.cultivo.refresh_from_db()
        self.assertEqual((self.cultivo.fecha_inicio_flora, self.cultivo.estado), (self.hoy, "floracion"))

    def test_corregir_la_fecha_de_la_primera_flora_mueve_el_contador(self):
        cambio = cambiar_etapa(self.cultivo, "flora_temprana", self.dia(3))
        self.client.post(reverse("growlog:cambio_etapa_cultivo_editar", args=[cambio.pk]),
                         {"etapa": "flora_temprana", "fecha_inicio": self.dia(10).isoformat(), "notas": ""})
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.fecha_inicio_flora, self.dia(10))

    def test_eliminar_la_etapa_de_flora_quita_el_contador(self):
        cambiar_etapa(self.cultivo, "veg_tardio", self.dia(30))
        flora = cambiar_etapa(self.cultivo, "flora_temprana", self.dia(5))
        self.client.post(reverse("growlog:cambio_etapa_cultivo_eliminar", args=[flora.pk]))
        self.cultivo.refresh_from_db()
        self.assertIsNone(self.cultivo.fecha_inicio_flora)
        self.assertEqual(self.cultivo.estado, "vegetativo")

    def test_cambiar_etapa_el_mismo_dia_corrige_en_vez_de_fallar(self):
        cambiar_etapa(self.cultivo, "veg_tardio", self.hoy)
        cambiar_etapa(self.cultivo, "flora_temprana", self.hoy)
        self.assertEqual(self.cultivo.cambios_etapa.count(), 1)
        self.assertEqual(etapa_efectiva_cultivo(self.cultivo), "flora_temprana")

    def test_finalizado_no_vuelve_a_activo_al_editar_etapas(self):
        cambiar_etapa(self.cultivo, "flora_tardia", self.dia(5))
        Cultivo.objects.filter(pk=self.cultivo.pk).update(estado="finalizado")
        self.cultivo.refresh_from_db()
        cambiar_etapa(self.cultivo, "secado", self.hoy)
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.estado, "finalizado")

    def test_el_vpd_ignora_la_etapa_de_una_sola_planta(self):
        parametro("flora_temprana", "1.00", "1.30")
        parametro("flora_tardia", "1.20", "1.50")
        cambiar_etapa(self.cultivo, "flora_temprana", self.dia(10))
        CambioEtapaPlanta.objects.create(planta=self.planta, etapa="flora_tardia", fecha_inicio=self.dia(1))
        m = MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=60)
        self.assertAlmostEqual(m.vpd, 1.27, places=1)
        self.assertEqual(m.vpd_estado, "ideal")  # rango de flora temprana (1.0–1.3), no el de la planta

    def test_planta_hereda_etapa_del_cultivo_salvo_etapa_propia_mas_reciente(self):
        cambiar_etapa(self.cultivo, "flora_temprana", self.dia(10))
        self.assertEqual(etapa_efectiva_planta(self.planta), "flora_temprana")
        CambioEtapaPlanta.objects.create(planta=self.planta, etapa="veg_tardio", fecha_inicio=self.dia(5))
        self.assertEqual(etapa_efectiva_planta(self.planta), "veg_tardio")
        cambiar_etapa(self.cultivo, "flora_tardia", self.dia(1))  # el cambio del cultivo, posterior, iguala
        self.assertEqual(etapa_efectiva_planta(self.planta), "flora_tardia")

    def test_semaforo_de_la_ficha_usa_la_etapa_de_la_medicion(self):
        parametro("veg_tardio", "0.80", "1.20")
        parametro("flora_tardia", "1.20", "1.50")
        cambiar_etapa(self.cultivo, "veg_tardio", self.dia(40))
        cambiar_etapa(self.cultivo, "flora_tardia", self.dia(5))
        MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=68,
                                        timestamp=timezone.now() - timedelta(days=20))
        response = self.client.get(reverse("growlog:cultivo_detail", args=[self.cultivo.slug]))
        self.assertEqual(response.context["semaforo"]["vpd"], "ideal")

    def test_nuevo_cultivo_crea_su_etapa_inicial(self):
        response = self.client.post(reverse("growlog:nuevo_cultivo"), {
            "nombre": "Nuevo", "fecha_inicio": self.hoy.isoformat(), "etapa_inicial": "plantula"})
        self.assertEqual(response.status_code, 302)
        nuevo = Cultivo.objects.get(nombre="Nuevo")
        self.assertEqual((nuevo.estado, etapa_efectiva_cultivo(nuevo)), ("plantula", "plantula"))

    def test_paginas_de_etapa_renderizan(self):
        cambiar_etapa(self.cultivo, "flora_temprana", self.dia(3))
        for url in (reverse("growlog:cultivo_etapa", args=[self.cultivo.slug]),
                    reverse("growlog:planta_etapa_list", args=[self.planta.pk]),
                    reverse("growlog:cultivo_detail", args=[self.cultivo.slug]),
                    reverse("growlog:cultivo_editar", args=[self.cultivo.slug]),
                    reverse("growlog:nuevo_cultivo")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_tendencias_trae_el_rango_vpd_de_cada_fecha(self):
        parametro("veg_tardio", "0.80", "1.20")
        parametro("flora_tardia", "1.20", "1.50")
        cambiar_etapa(self.cultivo, "veg_tardio", self.dia(40))
        cambiar_etapa(self.cultivo, "flora_tardia", self.dia(5))
        MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=60,
                                        timestamp=timezone.now() - timedelta(days=20))
        MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=60)
        datos = self.client.get(reverse("growlog:cultivo_tendencias_json", args=[self.cultivo.slug])).json()
        self.assertEqual([m["vpd_rango"] for m in datos["mediciones"]], [[0.8, 1.2], [1.2, 1.5]])

    def test_migracion_hereda_la_etapa_mas_avanzada_de_cada_fecha(self):
        CambioEtapaPlanta.objects.create(planta=self.planta, etapa="flora_temprana", fecha_inicio=self.dia(9))
        otra = Planta.objects.create(cultivo=self.cultivo, apodo="P2")
        CambioEtapaPlanta.objects.create(planta=otra, etapa="flora_tardia", fecha_inicio=self.dia(9))
        import_module("growlog.migrations.0029_etapa_cultivo").copiar_etapas(apps, None)
        self.assertEqual(list(CambioEtapaCultivo.objects.values_list("etapa", flat=True)), ["flora_tardia"])
        self.cultivo.refresh_from_db()
        self.assertEqual(self.cultivo.fecha_inicio_flora, self.dia(9))
