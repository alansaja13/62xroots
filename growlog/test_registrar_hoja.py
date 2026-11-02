"""Registrar como hoja: hora "ahora", mismo volumen, runoff, nota, planta, avisos y deshacer."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cultivo, Evento, MedicionAmbiente, MedicionPlanta, Planta, Riego, RiegoPlanta


class RegistrarHojaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("hoja")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate() - timedelta(days=10),
                                             propietario=cls.user, creado_por=cls.user)
        cls.luna = Planta.objects.create(cultivo=cls.cultivo, apodo="Luna")
        cls.sol = Planta.objects.create(cultivo=cls.cultivo, apodo="Sol")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("growlog:registrar")

    def post(self, kind, campos=None, **extra):
        datos = {"cultivo": self.cultivo.pk, "kind": kind, "observado_modo": "ahora",
                 **{f"{kind}-{k}": v for k, v in (campos or {}).items()}, **extra}
        return self.client.post(self.url, datos)

    def test_ahora_se_calcula_al_guardar(self):
        # La pantalla quedó abierta con una hora vieja: "ahora" usa la del envío.
        viejo = (timezone.localtime() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        self.post("ambiente", {"temperatura_c": "24", "humedad_relativa": "60"}, observado_en=viejo)
        medicion = MedicionAmbiente.objects.get()
        self.assertLess(timezone.now() - medicion.timestamp, timedelta(minutes=1))
        # Con "otra hora" vale la elegida.
        self.post("ambiente", {"temperatura_c": "24", "humedad_relativa": "60"}, observado_en=viejo, observado_modo="elegida")
        self.assertEqual(MedicionAmbiente.objects.order_by("timestamp").first().timestamp.hour,
                         (timezone.now() - timedelta(hours=3)).hour)

    def test_mismo_volumen_y_runoff(self):
        self.post("riego", {"mismo": "on", "volumen_todas": "375", "hubo_runoff": "on",
                            f"phrunoff-{self.luna.pk}": "6,5", f"ecrunoff-{self.sol.pk}": "9"})
        riego = Riego.objects.get()
        self.assertEqual(riego.volumen_total_ml, 750)
        self.assertTrue(riego.buscar_runoff)
        detalle = {d.planta_id: d for d in RiegoPlanta.objects.all()}
        self.assertTrue(detalle[self.luna.pk].runoff_observado)
        self.assertEqual(str(detalle[self.sol.pk].ec_runoff), "0.09")
        # Sin "Hubo runoff" los datos de drenaje no cuentan.
        self.post("riego", {"mismo": "on", "volumen_todas": "300", f"phrunoff-{self.luna.pk}": "6,5"})
        self.assertFalse(Riego.objects.latest("pk").detalle_plantas.filter(runoff_observado=True).exists())

    def test_error_de_volumen_dice_la_planta(self):
        page = self.post("riego", {f"planta-{self.luna.pk}": "0"})
        self.assertContains(page, "Revisá el riego de Luna.")
        self.assertIn(f"riego-planta-{self.luna.pk}", page.context["campos_error"])

    def test_nota_y_medicion_de_planta(self):
        self.post("nota", {"descripcion": "Hojas firmes"})
        self.assertEqual(Evento.objects.get().tipo, "nota")
        self.post("planta", {"planta_id": self.luna.pk, "altura_cm": "38,5", "nudos_count": "7", "aspecto_general": "bueno"})
        medicion = MedicionPlanta.objects.get()
        self.assertEqual((medicion.planta, str(medicion.altura_cm), medicion.fecha), (self.luna, "38.5", timezone.localdate()))
        page = self.post("planta", {"altura_cm": "10", "aspecto_general": "bueno"})
        self.assertContains(page, "Elegí la planta que mediste.")

    def test_avisos_se_confirman_uno_por_uno(self):
        page = self.post("ambiente", {"temperatura_c": "45", "humedad_relativa": "60"})
        self.assertContains(page, "poco comunes")
        clave = page.context["avisos_clave"]
        self.post("ambiente", {"temperatura_c": "45", "humedad_relativa": "60"}, aviso_ok=clave)
        self.assertEqual(MedicionAmbiente.objects.count(), 1)
        # Otro valor raro distinto vuelve a avisar aunque se mande la clave anterior.
        page = self.post("ambiente", {"temperatura_c": "46", "humedad_relativa": "60"}, aviso_ok=clave)
        self.assertContains(page, "poco comunes")
        self.assertEqual(MedicionAmbiente.objects.count(), 1)

    def test_hoja_vuelve_a_la_pantalla_y_deshace(self):
        hoja = self.client.get(self.url + f"?hoja=1&cultivo={self.cultivo.pk}", HTTP_HX_REQUEST="true",
                               HTTP_HX_CURRENT_URL="http://testserver/")
        self.assertContains(hoja, 'role="dialog"')
        self.assertNotContains(hoja, "<html")
        respuesta = self.post("nota", {"descripcion": "Algo"}, volver="/")
        self.assertRedirects(respuesta, "/", fetch_redirect_response=False)
        self.assertContains(self.client.get("/"), "Deshacer")
        self.client.post(reverse("growlog:registrar_deshacer"), {"volver": "/"})
        self.assertFalse(Evento.objects.exists())

    def test_deshacer_vence_al_minuto(self):
        self.post("nota", {"descripcion": "Algo"})
        with mock.patch("growlog.views.registrar.time.time", return_value=__import__("time").time() + 120):
            self.client.post(reverse("growlog:registrar_deshacer"))
        self.assertTrue(Evento.objects.exists())

    def test_repetir_trae_el_ultimo_riego(self):
        self.post("riego", {"mismo": "on", "volumen_todas": "400", "ph": "6,2", "ec": "140"})
        page = self.client.get(self.url + f"?cultivo={self.cultivo.pk}&kind=riego")
        ultimo = page.context["por_cultivo"][str(self.cultivo.pk)]["ultimo_riego"]
        self.assertEqual((ultimo["ph"], ultimo["ec"], ultimo["plantas"][str(self.luna.pk)]), ("6,2", "140", 400))
        self.assertContains(page, "Repetir riego del")
