"""<input type="date"> solo acepta YYYY-MM-DD: con es-ar Django localizaba el valor
a "16/08/2026", el navegador mostraba el campo vacío y al guardar se perdía la fecha."""

import re
from datetime import date, time
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CambioEtapaCultivo, CambioEtapaPlanta, CambioFotoperiodo, Cultivo, Evento,
    MedicionPlanta, Planta, Tarea,
)

# Día > 12 para que dd/mm y mm/dd no se puedan confundir.
FECHA = date(2026, 8, 16)

# Lo que el navegador acepta en cada tipo; cualquier otro value lo vacía (sanitización HTML).
_FORMATO_NAVEGADOR = {
    "date": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "datetime-local": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?"),
    "time": re.compile(r"\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?"),
}


class _FormScraper(HTMLParser):
    """Junta lo que el navegador enviaría de cada <form> tal como vino renderizado,
    incluida la sanitización de value en los inputs de fecha/hora."""

    def __init__(self):
        super().__init__()
        self.forms = []
        self._form = None
        self._select = None
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._form = {"fields": {}, "types": {}}
            self.forms.append(self._form)
        elif self._form is None:
            return
        elif tag == "input" and a.get("name"):
            tipo = a.get("type", "text")
            self._form["types"][a["name"]] = tipo
            if tipo in ("checkbox", "radio") and "checked" not in a:
                return
            valor = a.get("value", "on" if tipo == "checkbox" else "")
            formato = _FORMATO_NAVEGADOR.get(tipo)
            if formato and not formato.fullmatch(valor):
                valor = ""
            self._add(a["name"], valor)
        elif tag == "select":
            self._select = a.get("name")
        elif tag == "option" and self._select and "selected" in a:
            self._add(self._select, a.get("value", ""))
        elif tag == "textarea":
            self._textarea = a.get("name")
            self._add(self._textarea, "")

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None

    def handle_data(self, data):
        if self._textarea:
            self._form["fields"][self._textarea][-1] += data

    def _add(self, name, value):
        self._form["fields"].setdefault(name, []).append(value)


def _form_con(response, campo):
    scraper = _FormScraper()
    scraper.feed(response.content.decode())
    for form in scraper.forms:
        if campo in form["types"]:
            return form
    raise AssertionError(f"No se renderizó ningún form con el campo {campo!r}")


class DateInputIsoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("dueno", is_staff=True)
        cls.cultivo = Cultivo.objects.create(
            nombre="Fechas", fecha_inicio=FECHA, creado_por=cls.user, propietario=cls.user,
        )
        cls.planta = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")
        cls.tarea = Tarea.objects.create(cultivo=cls.cultivo, titulo="Revisar pH", fecha_objetivo=FECHA)
        cls.evento = Evento.objects.create(
            cultivo=cls.cultivo, tipo="problema", descripcion="Puntas quemadas",
            follow_up_fecha=FECHA, follow_up_descripcion="Mirar hojas nuevas",
        )
        cls.evento.plantas_afectadas.add(cls.planta)
        cls.medicion = MedicionPlanta.objects.create(planta=cls.planta, fecha=FECHA, altura_cm=40)
        cls.fotoperiodo = CambioFotoperiodo.objects.create(
            cultivo=cls.cultivo, fotoperiodo="12/12", hora_lights_on=time(8, 0), fecha_inicio=FECHA,
        )
        cls.etapa_cultivo = CambioEtapaCultivo.objects.create(
            cultivo=cls.cultivo, etapa="flora_temprana", fecha_inicio=FECHA,
        )
        cls.etapa_planta = CambioEtapaPlanta.objects.create(
            planta=cls.planta, etapa="flora_temprana", fecha_inicio=FECHA,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def assertFechaIso(self, url, campo, esperado):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        valor = _form_con(response, campo)["fields"].get(campo)
        self.assertEqual(valor, [esperado.isoformat()])

    def test_pantallas_de_edicion_renderizan_fecha_iso(self):
        casos = [
            ("cultivo_editar", self.cultivo.slug, "fecha_inicio"),
            ("tarea_editar", self.tarea.pk, "fecha_objetivo"),
            ("evento_editar", self.evento.pk, "follow_up_fecha"),
            ("medicion_planta_editar", self.medicion.pk, "fecha"),
            ("cambio_fotoperiodo_editar", self.fotoperiodo.pk, "fecha_inicio"),
            ("cambio_etapa_cultivo_editar", self.etapa_cultivo.pk, "fecha_inicio"),
            ("cambio_etapa_planta_editar", self.etapa_planta.pk, "fecha_inicio"),
        ]
        for nombre, arg, campo in casos:
            with self.subTest(vista=nombre):
                self.assertFechaIso(reverse(f"growlog:{nombre}", args=[arg]), campo, FECHA)

    def test_pantallas_de_alta_precargan_hoy_en_iso(self):
        hoy = timezone.localdate()
        casos = [
            (reverse("growlog:nuevo_cultivo"), "fecha_inicio"),
            (reverse("growlog:medicion_planta_crear", args=[self.planta.pk]), "fecha"),
            (reverse("growlog:fotoperiodo_list", args=[self.cultivo.slug]), "fecha_inicio"),
            (reverse("growlog:cultivo_etapa", args=[self.cultivo.slug]), "fecha_inicio"),
            (reverse("growlog:planta_etapa_list", args=[self.planta.pk]), "fecha_inicio"),
        ]
        for url, campo in casos:
            with self.subTest(url=url):
                self.assertFechaIso(url, campo, hoy)

    def _reenviar_sin_tocar(self, url, campo):
        form = _form_con(self.client.get(url), campo)
        response = self.client.post(url, form["fields"])
        self.assertEqual(response.status_code, 302)

    def test_guardar_tarea_sin_tocar_conserva_fecha_objetivo(self):
        self._reenviar_sin_tocar(reverse("growlog:tarea_editar", args=[self.tarea.pk]), "fecha_objetivo")
        self.tarea.refresh_from_db()
        self.assertEqual(self.tarea.fecha_objetivo, FECHA)
        self.assertEqual(self.tarea.titulo, "Revisar pH")

    def test_guardar_evento_sin_tocar_conserva_follow_up(self):
        self._reenviar_sin_tocar(reverse("growlog:evento_editar", args=[self.evento.pk]), "follow_up_fecha")
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.follow_up_fecha, FECHA)
        self.assertEqual(self.evento.follow_up_descripcion, "Mirar hojas nuevas")
        self.assertQuerySetEqual(self.evento.plantas_afectadas.all(), [self.planta])
