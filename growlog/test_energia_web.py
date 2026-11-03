from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CostoEnergetico, Cultivo, CultivoMiembro, Equipo, LecturaMedidor, TarifaElectrica


class EnergiaWebTests(TestCase):
    def setUp(self):
        self.duenio = User.objects.create_user("duenio")
        self.editor = User.objects.create_user("editor")
        self.hoy = timezone.localdate()
        self.cultivo = Cultivo.objects.create(nombre="Con luz", fecha_inicio=self.hoy - timedelta(days=10), propietario=self.duenio)
        CultivoMiembro.objects.create(cultivo=self.cultivo, usuario=self.editor, rol="editor")
        self.url = reverse("growlog:energia", args=[self.cultivo.slug])
        self.client.force_login(self.duenio)

    def post(self, **datos):
        return self.client.post(self.url, datos, follow=True)

    def tarifa(self):
        self.post(accion="tarifa", precio_kwh="100,5", fecha_desde=(self.hoy - timedelta(days=30)).isoformat(), distribuidora="Edenor")
        return TarifaElectrica.objects.get()

    def test_equipo_necesita_tarifa(self):
        self.assertContains(self.post(accion="equipo", nombre="LED", watts="200", horas_dia="18",
                                      fecha_desde=self.cultivo.fecha_inicio.isoformat()), "Primero cargá la tarifa")
        self.assertFalse(Equipo.objects.exists())

    def test_tarifa_y_equipo_nuevo_se_ven_en_el_cultivo(self):
        tarifa = self.tarifa()
        self.assertEqual((tarifa.precio_kwh, tarifa.propietario, tarifa.distribuidora), (Decimal("100.5"), self.duenio, "Edenor"))
        self.post(accion="equipo", nombre="LED", categoria="lampara", watts="200", horas_dia="18",
                  fecha_desde=self.cultivo.fecha_inicio.isoformat())
        costo = CostoEnergetico.objects.get()
        self.assertEqual((costo.equipo.nombre, costo.equipo.propietario, costo.tarifa), ("LED", self.duenio, tarifa))
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context["total_kwh_mes"], 108.0)
        self.assertEqual(respuesta.context["tarifa"], tarifa)

    def test_editar_y_sacar_equipo(self):
        self.tarifa()
        self.post(accion="equipo", nombre="Extractor", watts="50", horas_dia="24", fecha_desde=self.cultivo.fecha_inicio.isoformat())
        costo = CostoEnergetico.objects.get()
        self.post(accion="equipo_editar", pk=costo.pk, watts="40", horas_dia="12")
        costo.equipo.refresh_from_db()
        self.assertEqual((costo.equipo.watts, costo.equipo.horas_dia), (Decimal("40"), Decimal("12")))
        self.post(accion="equipo_quitar", pk=costo.pk)
        costo.refresh_from_db()
        self.assertEqual(costo.fecha_hasta, self.hoy)
        # El equipo vuelve a quedar disponible para sumarlo.
        self.assertEqual(self.client.get(self.url).context["equipos_disponibles"], [costo.equipo])

    def test_lecturas_se_corrigen_y_se_borran(self):
        self.post(accion="lectura", fecha=self.hoy.isoformat(), kwh_real="12,5")
        lectura = LecturaMedidor.objects.get()
        self.post(accion="lectura_editar", pk=lectura.pk, fecha=self.hoy.isoformat(), kwh_real="15", notas="medido de nuevo")
        lectura.refresh_from_db()
        self.assertEqual((lectura.kwh_real, lectura.notas), (Decimal("15"), "medido de nuevo"))
        self.assertContains(self.post(accion="lectura_editar", pk=lectura.pk, fecha=self.hoy.isoformat(), kwh_real="-3"), "kWh inválido")
        self.post(accion="lectura_borrar", pk=lectura.pk)
        self.assertFalse(LecturaMedidor.objects.exists())

    def test_editor_suma_equipos_pero_no_tarifas(self):
        self.tarifa()
        self.client.force_login(self.editor)
        self.assertContains(self.post(accion="tarifa", precio_kwh="1", fecha_desde=self.hoy.isoformat()), "la carga quien creó el cultivo")
        self.post(accion="equipo", nombre="Ventilador", watts="30", horas_dia="24", fecha_desde=self.hoy.isoformat())
        self.assertEqual(CostoEnergetico.objects.get().equipo.propietario, self.editor)

    def test_no_se_toca_lo_de_otro_cultivo(self):
        otro = Cultivo.objects.create(nombre="Otro", fecha_inicio=self.hoy, propietario=self.duenio)
        lectura = LecturaMedidor.objects.create(cultivo=otro, fecha=self.hoy, kwh_real=5)
        self.assertEqual(self.client.post(self.url, {"accion": "lectura_borrar", "pk": lectura.pk}).status_code, 404)
        self.assertTrue(LecturaMedidor.objects.filter(pk=lectura.pk).exists())
