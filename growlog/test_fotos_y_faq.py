"""Subida de fotos deshabilitada salvo permiso, y página de dudas frecuentes."""
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Cultivo, MedicionPlanta, Planta

# GIF de 1×1 píxel: imagen válida para el ImageField.
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
       b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


@override_settings(PERMITIR_FOTOS_A_TODOS=False)
class FotosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.duenio = User.objects.create_user("fotos-duenio")
        cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate(), propietario=cls.duenio)
        cls.planta = Planta.objects.create(cultivo=cultivo, apodo="P1")
        cls.url = reverse("growlog:medicion_planta_crear", args=[cls.planta.pk])

    def setUp(self):
        self.client.force_login(self.duenio)

    def enviar(self):
        foto = SimpleUploadedFile("p.gif", GIF, content_type="image/gif")
        return self.client.post(self.url, {"fecha": timezone.localdate().isoformat(),
                                           "aspecto_general": "bueno", "foto": foto})

    def test_sin_permiso_no_ve_el_campo_y_la_foto_se_ignora(self):
        page = self.client.get(self.url)
        self.assertNotContains(page, 'name="foto"')
        self.assertContains(page, "subida de fotos está deshabilitada")
        self.enviar()
        medicion = MedicionPlanta.objects.get(planta=self.planta)
        self.assertFalse(medicion.foto)

    def test_editar_sin_permiso_conserva_la_foto_existente(self):
        medicion = MedicionPlanta.objects.create(planta=self.planta, foto=SimpleUploadedFile("v.gif", GIF))
        nombre = medicion.foto.name
        self.client.post(reverse("growlog:medicion_planta_editar", args=[medicion.pk]),
                         {"fecha": medicion.fecha.isoformat(), "aspecto_general": "bueno"})
        medicion.refresh_from_db()
        self.assertEqual(medicion.foto.name, nombre)

    def test_con_permiso_puede_subir(self):
        self.duenio.user_permissions.add(Permission.objects.get(codename="subir_fotos"))
        self.assertContains(self.client.get(self.url), 'name="foto"')
        self.enviar()
        self.assertTrue(MedicionPlanta.objects.get(planta=self.planta).foto)

    @override_settings(PERMITIR_FOTOS_A_TODOS=True)
    def test_interruptor_global_habilita_a_todos(self):
        self.assertContains(self.client.get(self.url), 'name="foto"')


class FaqTests(TestCase):
    def test_requiere_sesion_y_muestra_temas(self):
        self.assertEqual(self.client.get(reverse("growlog:faq")).status_code, 302)
        self.client.force_login(User.objects.create_user("faq"))
        page = self.client.get(reverse("growlog:faq"))
        for texto in ("¿Qué es el pH", "¿Cómo se calcula el VPD?", "Araña roja", "¿Cuándo cosecho?"):
            self.assertContains(page, texto)
        self.assertContains(self.client.get("/"), reverse("growlog:faq"))
