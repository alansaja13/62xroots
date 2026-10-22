"""Navegación centrada en el cultivo: selector, pestañas, ajustes e inicio."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .context_processors import cultivos_del_menu
from .models import Cultivo, CultivoMiembro


class NavegacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        hoy = timezone.localdate()
        cls.duenio = User.objects.create_user("nav-duenio")
        cls.amigo = User.objects.create_user("nav-amigo")
        cls.propio = Cultivo.objects.create(nombre="Carpa propia", fecha_inicio=hoy, propietario=cls.duenio)
        cls.ajeno = Cultivo.objects.create(nombre="Carpa del amigo", fecha_inicio=hoy, propietario=cls.amigo)
        cls.cerrado = Cultivo.objects.create(nombre="Ciclo viejo", fecha_inicio=hoy, propietario=cls.duenio,
                                             estado="finalizado", fecha_fin=hoy)
        cls.archivado = Cultivo.objects.create(nombre="Ciclo guardado", fecha_inicio=hoy, propietario=cls.duenio,
                                               archivado=True)
        CultivoMiembro.objects.create(cultivo=cls.ajeno, usuario=cls.duenio, rol="lector")

    def setUp(self):
        self.client.force_login(self.duenio)

    def test_menu_agrupa_propios_compartidos_e_historial(self):
        grupos = cultivos_del_menu(self.duenio)
        self.assertEqual(grupos["activos"], [self.propio])
        self.assertEqual(grupos["compartidos"], [self.ajeno])
        self.assertEqual(grupos["compartidos"][0].rol_miembro, "lector")
        self.assertCountEqual(grupos["historial"], [self.cerrado, self.archivado])
        self.assertEqual(grupos["total"], 4)

    def test_inicio_separa_activos_compartidos_e_historial(self):
        page = self.client.get("/")
        self.assertContains(page, "Mis cultivos activos")
        self.assertContains(page, "Compartidos conmigo")
        self.assertContains(page, "Historial · 2")
        self.assertContains(page, "Solo lectura · de nav-amigo")
        # Al lector no se le ofrece registrar en el cultivo ajeno.
        self.assertNotContains(page, f"/registrar/?cultivo={self.ajeno.pk}")
        self.assertContains(page, f"/registrar/?cultivo={self.propio.pk}")

    def test_pestanas_del_cultivo_marcan_la_seccion(self):
        page = self.client.get(reverse("growlog:timeline", args=[self.propio.slug]))
        self.assertContains(page, 'class="cultivo-tabs"')
        self.assertEqual(page.context["seccion_cultivo"], "bitacora")
        self.assertContains(page, reverse("growlog:cultivo_ajustes", args=[self.propio.slug]))

    def test_lector_no_ve_ajustes_ni_puede_abrirlos(self):
        detalle = self.client.get(reverse("growlog:cultivo_detail", args=[self.ajeno.slug]))
        self.assertNotContains(detalle, reverse("growlog:cultivo_ajustes", args=[self.ajeno.slug]))
        ajustes = self.client.get(reverse("growlog:cultivo_ajustes", args=[self.ajeno.slug]))
        self.assertEqual(ajustes.status_code, 403)

    def test_formularios_no_muestran_las_pestanas(self):
        page = self.client.get(reverse("growlog:cultivo_editar", args=[self.propio.slug]))
        self.assertNotContains(page, 'class="cultivo-tabs"')

    def test_archivar_solo_el_propietario(self):
        url = reverse("growlog:cultivo_archivar", args=[self.propio.slug])
        self.client.post(url)
        self.propio.refresh_from_db()
        self.assertTrue(self.propio.archivado)
        self.client.post(url)
        self.propio.refresh_from_db()
        self.assertFalse(self.propio.archivado)

        CultivoMiembro.objects.filter(cultivo=self.ajeno).update(rol="editor")
        respuesta = self.client.post(reverse("growlog:cultivo_archivar", args=[self.ajeno.slug]))
        self.assertEqual(respuesta.status_code, 403)
        self.ajeno.refresh_from_db()
        self.assertFalse(self.ajeno.archivado)

    def test_registrar_propone_el_ultimo_cultivo_abierto(self):
        otro = Cultivo.objects.create(nombre="Segunda carpa", fecha_inicio=timezone.localdate(),
                                      propietario=self.duenio)
        for cultivo in (self.propio, otro):
            self.client.get(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
            self.assertEqual(self.client.get(reverse("growlog:registrar")).context["elegido"], cultivo)
