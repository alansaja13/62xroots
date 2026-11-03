from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CambioFotoperiodo, Cultivo, MedicionAmbiente, Planta
from .services.onboarding import pasos, recordar


class PrimerosPasosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nuevo")
        self.client.force_login(self.user)

    def crear(self):
        response = self.client.post(reverse("growlog:nuevo_cultivo"), {
            "nombre": "Primera", "fecha_inicio": timezone.localdate().isoformat(), "etapa_inicial": "plantula"})
        cultivo = Cultivo.objects.get(nombre="Primera")
        self.assertRedirects(response, reverse("growlog:cultivo_empezar", args=[cultivo.slug]))
        return cultivo

    def test_crear_lleva_a_los_pasos_y_se_completan(self):
        cultivo = self.crear()
        self.assertEqual(pasos(cultivo)["hechos"], 0)
        url = reverse("growlog:cultivo_empezar", args=[cultivo.slug])
        self.assertContains(self.client.get(url), "0 de 5")
        self.client.post(url, {"accion": "duracion", "duracion-dias_veg_estimados": 30, "duracion-dias_flora_estimados": 63})
        self.client.post(url, {"accion": "luz", "luz-lampara_modelo": "SF2000", "luz-lampara_watts_reales": 200})
        Planta.objects.create(cultivo=cultivo, apodo="A")
        CambioFotoperiodo.objects.create(cultivo=cultivo, fotoperiodo="18/6", hora_lights_on="08:00", fecha_inicio=cultivo.fecha_inicio)
        MedicionAmbiente.objects.create(cultivo=cultivo, temperatura_c=25, humedad_relativa=60)
        cultivo.refresh_from_db()
        self.assertEqual((cultivo.dias_flora_estimados, cultivo.lampara_watts_reales), (63, 200))
        self.assertTrue(pasos(cultivo)["completo"])
        self.assertIsNone(recordar(cultivo))

    def test_duracion_incompleta_no_se_guarda(self):
        cultivo = self.crear()
        response = self.client.post(reverse("growlog:cultivo_empezar", args=[cultivo.slug]),
                                    {"accion": "duracion", "duracion-dias_veg_estimados": 30})
        self.assertEqual(response.status_code, 200)
        cultivo.refresh_from_db()
        self.assertIsNone(cultivo.dias_veg_estimados)

    def test_el_resumen_recuerda_los_pasos_solo_al_principio(self):
        cultivo = self.crear()
        detalle = reverse("growlog:cultivo_detail", args=[cultivo.slug])
        self.assertContains(self.client.get(detalle), "Primeros pasos")
        Cultivo.objects.filter(pk=cultivo.pk).update(fecha_inicio=timezone.localdate() - timezone.timedelta(days=40))
        self.assertNotContains(self.client.get(detalle), "Primeros pasos")

    def test_varias_plantas_con_apodos(self):
        cultivo = self.crear()
        response = self.client.post(reverse("growlog:planta_crear", args=[cultivo.slug]), {
            "cantidad": 3, "strain": "Lemon Haze", "tipo": "auto", "apodo-1": "Luna", "apodo-2": "", "apodo-3": "Sol",
            "siguiente": "empezar"})
        self.assertRedirects(response, reverse("growlog:cultivo_empezar", args=[cultivo.slug]))
        plantas = list(cultivo.plantas.order_by("pk").values_list("apodo", "strain", "tipo", "creado_por"))
        self.assertEqual(plantas, [("Luna", "Lemon Haze", "auto", self.user.pk), ("Lemon Haze 2", "Lemon Haze", "auto", self.user.pk),
                                   ("Sol", "Lemon Haze", "auto", self.user.pk)])

    def test_cantidad_fuera_de_rango(self):
        cultivo = self.crear()
        response = self.client.post(reverse("growlog:planta_crear", args=[cultivo.slug]), {"cantidad": 40, "tipo": "foto"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(cultivo.plantas.exists())

    def test_lector_no_entra(self):
        otro = User.objects.create_user(username="dueno")
        cultivo = Cultivo.objects.create(nombre="Ajeno", fecha_inicio=timezone.localdate(), propietario=otro)
        self.assertEqual(self.client.get(reverse("growlog:cultivo_empezar", args=[cultivo.slug])).status_code, 404)
