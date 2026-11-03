from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cultivo, CultivoMiembro, Invitacion


class InvitacionTests(TestCase):
    def setUp(self):
        self.duenio = User.objects.create_user("duenio")
        self.cultivo = Cultivo.objects.create(nombre="Compartido", fecha_inicio=timezone.localdate(), propietario=self.duenio)
        self.inv = Invitacion.objects.create(cultivo=self.cultivo, rol="editor", creada_por=self.duenio)
        self.url = reverse("growlog:invitacion_aceptar", args=[self.inv.token])

    def test_crea_cuenta_y_queda_como_miembro(self):
        self.assertContains(self.client.get(self.url), "Crear mi cuenta")
        response = self.client.post(self.url, {"username": "amiga", "password1": "una-clave-larga-42", "password2": "una-clave-larga-42"})
        self.assertRedirects(response, reverse("growlog:cultivo_detail", args=[self.cultivo.slug]))
        usuario = User.objects.get(username="amiga")
        self.assertTrue(usuario.check_password("una-clave-larga-42"))
        self.assertFalse(usuario.is_staff)
        self.assertEqual(CultivoMiembro.objects.get(usuario=usuario).rol, "editor")
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.usada_por, usuario)
        # Ya usado: no sirve otra vez.
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 410)

    def test_clave_debil_no_crea_nada(self):
        response = self.client.post(self.url, {"username": "amiga", "password1": "123", "password2": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="amiga").exists())
        self.inv.refresh_from_db()
        self.assertTrue(self.inv.vigente)

    def test_cuenta_existente_se_suma_y_no_baja_permisos(self):
        otro = User.objects.create_user("otro")
        self.client.force_login(otro)
        self.assertContains(self.client.get(self.url), "Sumarme como otro")
        self.client.post(self.url)
        self.assertEqual(CultivoMiembro.objects.get(usuario=otro).rol, "editor")
        lector = Invitacion.objects.create(cultivo=self.cultivo, rol="lector", creada_por=self.duenio)
        self.client.post(reverse("growlog:invitacion_aceptar", args=[lector.token]))
        self.assertEqual(CultivoMiembro.objects.get(usuario=otro).rol, "editor")

    def test_vencida_o_anulada(self):
        Invitacion.objects.filter(pk=self.inv.pk).update(vence=timezone.now() - timedelta(minutes=1))
        self.assertContains(self.client.get(self.url), "Venció", status_code=410)
        self.assertEqual(self.client.get(reverse("growlog:invitacion_aceptar", args=["nada"])).status_code, 410)

    def test_solo_quien_la_creo_la_anula(self):
        otro = User.objects.create_user("otro")
        self.client.force_login(otro)
        self.assertEqual(self.client.post(reverse("growlog:invitacion_revocar", args=[self.inv.pk])).status_code, 404)
        self.client.force_login(self.duenio)
        self.client.post(reverse("growlog:invitacion_revocar", args=[self.inv.pk]))
        self.assertFalse(Invitacion.objects.exists())

    def test_el_duenio_que_abre_su_link_no_se_suma(self):
        self.client.force_login(self.duenio)
        self.client.post(self.url)
        self.assertFalse(CultivoMiembro.objects.exists())
