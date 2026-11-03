from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (CambioFotoperiodo, CostoEnergetico, Cultivo, Equipo, MedicionAmbiente, MedicionPlanta,
                     ParametroIdeal, Planta, TarifaElectrica)
from .services.etapas import cambiar_etapa
from .services.reporte import cifras, reporte


class ReporteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("rep")
        self.client.force_login(self.user)
        self.hoy = timezone.localdate()
        self.cultivo = Cultivo.objects.create(nombre="Cerrado", fecha_inicio=self.hoy - timedelta(days=20), propietario=self.user,
                                              lampara_watts_reales=100)
        cambiar_etapa(self.cultivo, "veg_tardio", self.cultivo.fecha_inicio)
        ParametroIdeal.objects.update_or_create(etapa="veg_tardio", defaults=dict(
            temp_min=20, temp_max=28, hr_min=50, hr_max=70, vpd_min=0.8, vpd_max=1.2, ph_min=6, ph_max=7))
        self.a = Planta.objects.create(cultivo=self.cultivo, apodo="A", yield_estimado_g=100, yield_real_g=80, peso_humedo_g=400)
        self.b = Planta.objects.create(cultivo=self.cultivo, apodo="B", yield_real_g=120, peso_humedo_g=600)
        Planta.objects.create(cultivo=self.cultivo, apodo="Muerta", estado="descartada", yield_estimado_g=50)

    def medir(self, dias, temp, hr):
        return MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=temp, humedad_relativa=hr,
                                               timestamp=timezone.now() - timedelta(days=dias))

    def test_cifras_de_cierre(self):
        self.medir(15, 25, 60)   # VPD ~1,27: alto
        self.medir(10, 25, 65)   # ~1,11: ideal
        self.medir(2, 24, 65)    # ~1,04: ideal
        datos = reporte(Cultivo.objects.get(pk=self.cultivo.pk))
        self.assertEqual((datos["seco"], datos["estimado"], datos["g_por_watt"], datos["g_por_planta"]), (200, 100, 2.0, 100))
        self.assertEqual(datos["merma"], 80)
        self.assertEqual(datos["en_rango"], 67)
        self.assertEqual([s["pct"] for s in datos["en_rango_detalle"]["semanas"]], [0, 100, 100])
        self.assertEqual([y["real_pct"] for y in datos["yield_plantas"]], [67, 100])

    def test_energia_por_equipos_y_tarifa(self):
        equipo = Equipo.objects.create(nombre="LED", watts=100, horas_dia=10, categoria="lampara", propietario=self.user)
        tarifa = TarifaElectrica.objects.create(fecha_desde=self.cultivo.fecha_inicio - timedelta(days=30), precio_kwh=100)
        CostoEnergetico.objects.create(cultivo=self.cultivo, equipo=equipo, tarifa=tarifa, fecha_desde=self.cultivo.fecha_inicio)
        energia = cifras(self.cultivo)["energia"]
        # 21 días × 1 kWh = 21 kWh × $100 = $2100; 200 g → $10,5 por gramo.
        self.assertEqual((energia["kwh"], energia["costo"], energia["fuente"]), (21.0, 2100, "equipos"))
        self.assertEqual(energia["costo_por_gramo"], 10)

    def test_sin_equipos_estima_con_la_lampara(self):
        CambioFotoperiodo.objects.create(cultivo=self.cultivo, fotoperiodo="18/6", hora_lights_on=time(6), fecha_inicio=self.cultivo.fecha_inicio)
        energia = cifras(self.cultivo)["energia"]
        self.assertEqual((energia["kwh"], energia["fuente"], energia["costo"]), (37.8, "lampara", None))

    def test_crecimiento_y_comparacion(self):
        MedicionPlanta.objects.create(planta=self.a, fecha=self.cultivo.fecha_inicio + timedelta(days=2), altura_cm=10)
        MedicionPlanta.objects.create(planta=self.a, fecha=self.cultivo.fecha_inicio + timedelta(days=12), altura_cm=40)
        viejo = Cultivo.objects.create(nombre="Anterior", fecha_inicio=self.hoy - timedelta(days=200), propietario=self.user,
                                       estado="finalizado", fecha_fin=self.hoy - timedelta(days=100))
        Planta.objects.create(cultivo=viejo, apodo="V", yield_real_g=50)
        Cultivo.objects.create(nombre="Ajeno", fecha_inicio=self.hoy, estado="finalizado", fecha_fin=self.hoy)
        respuesta = self.client.get(reverse("growlog:reporte", args=[self.cultivo.slug]))
        self.assertEqual(len(respuesta.context["crecimiento"]["lineas"]), 1)
        self.assertEqual([a["cultivo"].nombre for a in respuesta.context["anteriores"]], ["Anterior"])
        self.assertEqual(respuesta.context["anteriores"][0]["dias"], 100)
        self.assertContains(respuesta, "Contra tus cultivos anteriores")
