"""Un lector no ve accesos de edición que le devolverían 403."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CambioEtapaPlanta, Cultivo, CultivoMiembro, Evento, MedicionPlanta, Planta, Riego,
)
from .services.riegos import guardar_riego


class LectorSinAccesosDeEdicionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        hoy = timezone.localdate()
        cls.duenio = User.objects.create_user("duenio")
        cls.lector = User.objects.create_user("lector")
        cls.cultivo = Cultivo.objects.create(nombre="Compartido", fecha_inicio=hoy, creado_por=cls.duenio)
        cls.vacio = Cultivo.objects.create(nombre="Sin plantas", fecha_inicio=hoy, creado_por=cls.duenio)
        for cultivo in (cls.cultivo, cls.vacio):
            CultivoMiembro.objects.create(cultivo=cultivo, usuario=cls.lector, rol="lector")
        cls.planta = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")
        riego = guardar_riego(riego=Riego(cultivo=cls.cultivo), detalles=[
            {"planta": cls.planta, "volumen_ml": 500},
        ])
        evento = Evento.objects.create(
            cultivo=cls.cultivo, tipo="problema", descripcion="manchas",
            follow_up_fecha=hoy, follow_up_descripcion="revisar",
        )
        evento.plantas_afectadas.add(cls.planta)
        medicion = MedicionPlanta.objects.create(planta=cls.planta, altura_cm=Decimal("30"))
        CambioEtapaPlanta.objects.create(planta=cls.planta, etapa="flora_temprana", fecha_inicio=hoy)
        cls.urls_de_edicion = [
            reverse("growlog:riego_editar", args=[riego.pk]),
            reverse("growlog:evento_editar", args=[evento.pk]),
            reverse("growlog:medicion_planta_editar", args=[medicion.pk]),
            reverse("growlog:medicion_planta_crear", args=[cls.planta.pk]),
            reverse("growlog:planta_crear", args=[cls.vacio.slug]),
            reverse("growlog:registrar") + f"?cultivo={cls.cultivo.pk}",
        ]
        cls.paginas = [
            reverse("growlog:cultivo_detail", args=[cls.cultivo.slug]),
            reverse("growlog:cultivo_detail", args=[cls.vacio.slug]),
            reverse("growlog:planta_detail", args=[cls.planta.pk]),
            reverse("growlog:tareas_list", args=[cls.cultivo.slug]),
            reverse("growlog:planta_etapa_list", args=[cls.planta.pk]),
        ]

    def test_lector_no_ve_accesos_de_edicion(self):
        self.client.force_login(self.lector)
        for pagina in self.paginas:
            respuesta = self.client.get(pagina)
            self.assertEqual(respuesta.status_code, 200, pagina)
            for url in self.urls_de_edicion:
                self.assertNotContains(respuesta, f'href="{url}', msg_prefix=pagina)

    def test_propietario_conserva_los_accesos(self):
        self.client.force_login(self.duenio)
        contenido = "".join(self.client.get(p).content.decode() for p in self.paginas)
        for url in self.urls_de_edicion:
            self.assertIn(f'href="{url}', contenido)

    def test_lector_ve_historial_de_etapas_de_planta_sin_formulario(self):
        self.client.force_login(self.lector)
        url = reverse("growlog:planta_etapa_list", args=[self.planta.pk])
        respuesta = self.client.get(url)
        self.assertContains(respuesta, "Flora temprana")
        self.assertIsNone(respuesta.context["form"])
        self.assertNotContains(respuesta, reverse("growlog:cambio_etapa_planta_editar", args=[
            self.planta.cambios_etapa.get().pk]))

    def test_lector_no_puede_cambiar_etapa_de_planta(self):
        self.client.force_login(self.lector)
        url = reverse("growlog:planta_etapa_list", args=[self.planta.pk])
        respuesta = self.client.post(url, {"etapa": "flora_tardia", "fecha_inicio": "2026-01-01"})
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.planta.cambios_etapa.count(), 1)
