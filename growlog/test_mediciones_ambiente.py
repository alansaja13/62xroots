"""Corrección y borrado de mediciones de ambiente desde la web."""
from datetime import datetime, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CambioFotoperiodo, Cultivo, CultivoMiembro, Evento, MedicionAmbiente


def local(hora, minuto=0):
    """Hoy a la hora local indicada, como datetime con zona horaria."""
    return timezone.make_aware(datetime.combine(timezone.localdate(), time(hora, minuto)))


class MedicionAmbienteWebTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.duenio = User.objects.create_user("duenio")
        cls.lector = User.objects.create_user("lector")
        cls.ajeno = User.objects.create_user("ajeno")
        cls.cultivo = Cultivo.objects.create(
            nombre="Ambiente", fecha_inicio=timezone.localdate(), creado_por=cls.duenio,
        )
        CultivoMiembro.objects.create(cultivo=cls.cultivo, usuario=cls.lector, rol="lector")
        # Luz de 08:00 a 20:00: una medición a las 10 es de día y a las 22, de noche.
        CambioFotoperiodo.objects.create(
            cultivo=cls.cultivo, fotoperiodo="12/12", hora_lights_on=time(8, 0),
            fecha_inicio=timezone.localdate(),
        )

    def setUp(self):
        self.medicion = MedicionAmbiente.objects.create(
            cultivo=self.cultivo, timestamp=local(10), temperatura_c=Decimal("26.5"),
            humedad_relativa=Decimal("60"), creado_por=self.duenio,
        )
        self.url = reverse("growlog:medicion_ambiente_editar", args=[self.medicion.pk])

    def datos(self, **cambios):
        datos = {
            "timestamp": timezone.localtime(self.medicion.timestamp).strftime("%Y-%m-%dT%H:%M"),
            "temperatura_c": "26.5", "humedad_relativa": "60", "notas": "",
        }
        datos.update(cambios)
        return datos

    def test_editor_corrige_valores(self):
        self.client.force_login(self.duenio)
        response = self.client.post(self.url, self.datos(temperatura_c="24.8", humedad_relativa="55", notas="sensor movido"))
        self.assertRedirects(response, reverse("growlog:cultivo_detail", args=[self.cultivo.slug]))
        self.medicion.refresh_from_db()
        self.assertEqual(self.medicion.temperatura_c, Decimal("24.8"))
        self.assertEqual(self.medicion.humedad_relativa, Decimal("55"))
        self.assertEqual(self.medicion.notas, "sensor movido")

    def test_cambiar_hora_recalcula_luz(self):
        self.assertEqual(self.medicion.luz_estado, "on")
        self.client.force_login(self.duenio)
        hora = local(22).strftime("%Y-%m-%dT%H:%M")
        self.client.post(self.url, self.datos(timestamp=hora))
        self.medicion.refresh_from_db()
        self.assertEqual(self.medicion.luz_estado, "off")

    def test_valor_fuera_de_rango_no_se_guarda(self):
        self.client.force_login(self.duenio)
        response = self.client.post(self.url, self.datos(temperatura_c="254"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["temperatura_c"])
        self.medicion.refresh_from_db()
        self.assertEqual(self.medicion.temperatura_c, Decimal("26.5"))

    def test_formulario_muestra_la_hora_guardada(self):
        self.client.force_login(self.duenio)
        response = self.client.get(self.url)
        self.assertContains(response, f'value="{local(10).strftime("%Y-%m-%dT%H:%M")}"')

    def test_editor_elimina(self):
        self.client.force_login(self.duenio)
        response = self.client.post(reverse("growlog:medicion_ambiente_eliminar", args=[self.medicion.pk]))
        self.assertRedirects(response, reverse("growlog:cultivo_detail", args=[self.cultivo.slug]))
        self.assertFalse(MedicionAmbiente.objects.filter(pk=self.medicion.pk).exists())

    def test_lector_no_puede_corregir_ni_eliminar(self):
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.datos(temperatura_c="20")).status_code, 403)
        eliminar = reverse("growlog:medicion_ambiente_eliminar", args=[self.medicion.pk])
        self.assertEqual(self.client.post(eliminar).status_code, 403)
        self.medicion.refresh_from_db()
        self.assertEqual(self.medicion.temperatura_c, Decimal("26.5"))

    def test_usuario_sin_acceso_recibe_404(self):
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_enlace_de_correccion_solo_para_quien_edita(self):
        evento = Evento.objects.create(cultivo=self.cultivo, tipo="otro", descripcion="nota")
        editar_evento = reverse("growlog:evento_editar", args=[evento.pk])
        for vista in ("cultivo_detail", "timeline"):
            pagina = reverse(f"growlog:{vista}", args=[self.cultivo.slug])
            self.client.force_login(self.duenio)
            self.assertContains(self.client.get(pagina), self.url)
            self.client.force_login(self.lector)
            respuesta = self.client.get(pagina)
            self.assertEqual(respuesta.status_code, 200)
            self.assertNotContains(respuesta, self.url)
            # Tampoco ve la edición de otros registros, que le daría 403.
            self.assertNotContains(respuesta, editar_evento)
