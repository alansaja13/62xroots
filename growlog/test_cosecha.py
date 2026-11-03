from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cultivo, CultivoMiembro, Planta
from .services.etapas import cambiar_etapa
from .utils import etapa_efectiva_cultivo


class CosechaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cosecha")
        self.lector = User.objects.create_user("mira")
        self.hoy = timezone.localdate()
        self.cultivo = Cultivo.objects.create(nombre="Para cortar", fecha_inicio=self.hoy - timedelta(days=90),
                                              propietario=self.user, lampara_watts_reales=200)
        CultivoMiembro.objects.create(cultivo=self.cultivo, usuario=self.lector, rol="lector")
        cambiar_etapa(self.cultivo, "flora_tardia", self.hoy - timedelta(days=20))
        self.a = Planta.objects.create(cultivo=self.cultivo, apodo="A")
        self.b = Planta.objects.create(cultivo=self.cultivo, apodo="B")
        Planta.objects.create(cultivo=self.cultivo, apodo="Muerta", estado="descartada")
        self.url = reverse("growlog:cultivo_cosecha", args=[self.cultivo.slug])
        self.client.force_login(self.user)

    def post(self, **datos):
        return self.client.post(self.url, datos)

    def test_cosecha_completa(self):
        ayer = (self.hoy - timedelta(days=1)).isoformat()
        self.post(accion="cortar", plantas=[self.a.pk, self.b.pk], fecha=ayer, etapa="1")
        self.a.refresh_from_db()
        self.assertEqual((self.a.estado, self.a.fecha_corte.isoformat()), ("cosechada", ayer))
        self.assertEqual(etapa_efectiva_cultivo(Cultivo.objects.get(pk=self.cultivo.pk)), "secado")

        self.post(accion="pesar", **{f"peso-{self.a.pk}": "400", f"peso-{self.b.pk}": "600"})
        self.post(accion="secar", fecha=self.hoy.isoformat(), etapa="1", **{f"peso-{self.a.pk}": "100", f"peso-{self.b.pk}": "150,4"})
        self.b.refresh_from_db()
        self.assertEqual((self.b.peso_humedo_g, self.b.yield_real_g, self.b.fecha_seco), (600, 150, self.hoy))
        self.assertEqual(etapa_efectiva_cultivo(Cultivo.objects.get(pk=self.cultivo.pk)), "curado")

        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context["seco_total"], 250)
        self.assertEqual(respuesta.context["merma"], 75)
        self.assertEqual(respuesta.context["g_por_watt"], 1.25)
        self.assertEqual(respuesta.context["actual"], "cerrar")
        self.assertEqual([p.apodo for p in respuesta.context["plantas"]], ["A", "B"])

        self.assertRedirects(self.post(accion="cerrar"), reverse("growlog:reporte", args=[self.cultivo.slug]))
        self.cultivo.refresh_from_db()
        self.assertEqual((self.cultivo.estado, self.cultivo.fecha_fin), ("finalizado", self.hoy))

    def test_cortar_en_tandas(self):
        self.post(accion="cortar", plantas=[self.a.pk], fecha=self.hoy.isoformat())
        datos = self.client.get(self.url).context
        self.assertEqual([p.apodo for p in datos["sin_cortar"]], ["B"])
        self.assertEqual(datos["actual"], "cortar")
        # Sin marcar el cambio de etapa, el cultivo sigue en flora.
        self.assertEqual(etapa_efectiva_cultivo(Cultivo.objects.get(pk=self.cultivo.pk)), "flora_tardia")

    def test_errores_no_guardan(self):
        futuro = (self.hoy + timedelta(days=2)).isoformat()
        self.assertContains(self.post(accion="cortar", plantas=[self.a.pk], fecha=futuro), "La fecha tiene que estar")
        self.assertContains(self.post(accion="cortar", fecha=self.hoy.isoformat()), "Elegí al menos una planta")
        self.post(accion="cortar", plantas=[self.a.pk], fecha=self.hoy.isoformat())
        self.assertContains(self.post(accion="secar", **{f"peso-{self.a.pk}": "mucho"}), "no es válido")
        self.a.refresh_from_db()
        self.assertIsNone(self.a.yield_real_g)

    def test_lector_no_entra(self):
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.post(accion="cerrar").status_code, 403)
