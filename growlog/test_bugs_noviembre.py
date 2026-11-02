"""Regresiones de los bugs encontrados en el relevamiento de noviembre 2026."""
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CambioFotoperiodo, Cultivo, Evento, MedicionAmbiente, MedicionEC, Nutriente, NutrienteAplicado, Planta, Riego, Tarea,
)
from .utils import area_carpa_m2


class BugsNoviembreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("duena")
        hoy = timezone.localdate()
        cls.cultivo = Cultivo.objects.create(
            nombre="Carpa", fecha_inicio=hoy - timedelta(days=30), creado_por=cls.owner, propietario=cls.owner,
        )
        cls.planta = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")

    def setUp(self):
        self.client.force_login(self.owner)

    def mensajes(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    # Concordancia del mensaje de Registrar.
    def test_registrar_tarea_dice_guardada(self):
        response = self.client.post(reverse("growlog:registrar"), {
            "cultivo": self.cultivo.pk, "kind": "tarea", "tarea-titulo": "Revisar",
            "tarea-categoria": "observacion", "tarea-prioridad": "normal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("Tarea guardada en Carpa.", self.mensajes(response))

    # Completar desde el formulario de edición guarda la fecha; reabrir la limpia.
    def test_editar_tarea_completada_guarda_y_limpia_fecha(self):
        tarea = Tarea.objects.create(cultivo=self.cultivo, titulo="Podar")
        datos = {"tarea-titulo": "Podar", "tarea-prioridad": "normal", "tarea-categoria": "training"}
        self.client.post(reverse("growlog:tarea_editar", args=[tarea.pk]), {**datos, "tarea-completada": "on"})
        tarea.refresh_from_db()
        self.assertTrue(tarea.completada)
        self.assertIsNotNone(tarea.completada_en)
        self.client.post(reverse("growlog:tarea_editar", args=[tarea.pk]), datos)
        tarea.refresh_from_db()
        self.assertIsNone(tarea.completada_en)

    # Desde la lista de tareas no se manda el OOB a un panel que ahí no existe.
    def test_completar_desde_lista_no_manda_oob(self):
        tarea = Tarea.objects.create(cultivo=self.cultivo, titulo="Regar")
        response = self.client.post(reverse("growlog:tarea_completar", args=[tarea.pk]),
                                    {"origen": "lista"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.content, b"")
        response = self.client.post(reverse("growlog:tarea_descompletar", args=[tarea.pk]), HTTP_HX_REQUEST="true")
        response = self.client.post(reverse("growlog:tarea_completar", args=[tarea.pk]), HTTP_HX_REQUEST="true")
        self.assertContains(response, "tareas-done")

    # La bitácora muestra el tipo legible y no imprime "None" sin rango ideal.
    def test_bitacora_tipo_legible_y_sin_none(self):
        Evento.objects.create(cultivo=self.cultivo, tipo="ajuste_ambiente", descripcion="Subí el extractor")
        MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=25, humedad_relativa=60)
        for nombre in ("growlog:timeline", "growlog:cultivo_detail"):
            response = self.client.get(reverse(nombre, args=[self.cultivo.slug]))
            self.assertNotContains(response, ">ajuste_ambiente<")
            self.assertContains(response, "juste de ambiente")  # "Ajuste…" en el Resumen, "ajuste…" en la bitácora
            self.assertNotContains(response, "· None")

    # Energía no repite los mensajes que ya muestra base.html.
    def test_energia_no_duplica_mensajes(self):
        response = self.client.post(reverse("growlog:energia", args=[self.cultivo.slug]),
                                    {"fecha": timezone.localdate().isoformat(), "kwh_real": "10"}, follow=True)
        textos = self.mensajes(response)
        self.assertTrue(textos)
        self.assertEqual(response.content.decode().count(textos[0]), 1)

    # La edición de pH/EC valida igual que Registrar.
    def test_editar_ec_exige_valor_y_ph_en_rango(self):
        medicion = MedicionEC.objects.create(cultivo=self.cultivo, ph=6)
        url = reverse("growlog:medicion_ec_editar", args=[medicion.pk])
        base = {"observado_modo": "elegida", "observado_en": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "ec-tipo": "solucion"}
        self.assertContains(self.client.post(url, base), "al menos uno de los dos")
        self.assertIn("ec-ph", self.client.post(url, {**base, "ec-ph": "20"}).context["campos_error"])
        medicion.refresh_from_db()
        self.assertEqual(medicion.ph, 6)

    def test_dosis_editada_debe_ser_positiva(self):
        riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=1000)
        nutriente = Nutriente.objects.create(nombre="Grow")
        url = reverse("growlog:riego_editar", args=[riego.pk])
        response = self.client.post(url, {
            "observado_modo": "ahora", f"riego-planta-{self.planta.pk}": "500", f"riego-nutriente-{nutriente.pk}": "0"})
        self.assertIn("riego-dosis_g_por_litro", response.context["campos_error"])
        self.assertFalse(NutrienteAplicado.objects.exists())
        # Con una dosis válida se guarda: la dosis se corrige en el mismo formulario.
        self.client.post(url, {"observado_modo": "ahora", f"riego-planta-{self.planta.pk}": "500",
                               f"riego-nutriente-{nutriente.pk}": "1,5"})
        self.assertEqual(str(NutrienteAplicado.objects.get().dosis_g_por_litro), "1.500")

    # Un fotoperíodo programado a futuro no se marca como activo.
    def test_fotoperiodo_futuro_no_es_activo(self):
        hoy = timezone.localdate()
        CambioFotoperiodo.objects.create(cultivo=self.cultivo, fotoperiodo="18/6", hora_lights_on=time(6), fecha_inicio=hoy - timedelta(days=10))
        CambioFotoperiodo.objects.create(cultivo=self.cultivo, fotoperiodo="12/12", hora_lights_on=time(6), fecha_inicio=hoy + timedelta(days=3))
        response = self.client.get(reverse("growlog:fotoperiodo_list", args=[self.cultivo.slug]))
        self.assertEqual(response.context["activo"].fotoperiodo, "18/6")
        self.assertContains(response, "programado")

    # Reporte sin atributos style duplicados.
    def test_reporte_sin_style_duplicado(self):
        response = self.client.get(reverse("growlog:reporte", args=[self.cultivo.slug]))
        self.assertNotRegex(response.content.decode(), r'style="[^"]*"[^>]*style="')

    # Canopy usa la carpa y la lámpara reales, sin valores inventados.
    def test_area_carpa(self):
        self.assertEqual(area_carpa_m2("80x80x180"), 0.64)
        self.assertEqual(area_carpa_m2("120 x 60"), 0.72)
        self.assertIsNone(area_carpa_m2(""))
        self.assertIsNone(area_carpa_m2("grande"))

    def test_canopy_sin_lampara_no_inventa_watts(self):
        response = self.client.get(reverse("growlog:canopy", args=[self.cultivo.slug]))
        self.assertIsNone(response.context["init_data"]["watts"])
        self.assertIsNone(response.context["init_data"]["area_m2"])

    # Las plantas archivadas se pueden encontrar desde el resumen.
    def test_resumen_lista_plantas_archivadas(self):
        archivada = Planta.objects.create(cultivo=self.cultivo, apodo="Vieja", archivado=True)
        response = self.client.get(reverse("growlog:cultivo_detail", args=[self.cultivo.slug]))
        self.assertContains(response, "archivadas · 1")
        self.assertContains(response, reverse("growlog:planta_detail", args=[archivada.pk]))


class MapaVpdTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import ParametroIdeal
        from .services.etapas import cambiar_etapa
        cls.owner = User.objects.create_user("vpd")
        hoy = timezone.localdate()
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=hoy - timedelta(days=40), propietario=cls.owner)
        cambiar_etapa(cls.cultivo, "veg_temprano", hoy - timedelta(days=40))
        cambiar_etapa(cls.cultivo, "flora_temprana", hoy - timedelta(days=3))
        for etapa, vmin, vmax in (("veg_temprano", "0.8", "1.0"), ("flora_temprana", "1.0", "1.3"), ("secado", "0", "0")):
            ParametroIdeal.objects.update_or_create(etapa=etapa, defaults=dict(
                temp_min=20, temp_max=28, hr_min=40, hr_max=70, ph_min=6, ph_max=7, vpd_min=vmin, vpd_max=vmax))
        ahora = timezone.now()
        # 24,2° y 62% dan 1,15 kPa: alto en veg temprano, ideal en flora temprana.
        MedicionAmbiente.objects.create(cultivo=cls.cultivo, temperatura_c=24.2, humedad_relativa=62, timestamp=ahora - timedelta(days=6))
        MedicionAmbiente.objects.create(cultivo=cls.cultivo, temperatura_c=24.2, humedad_relativa=62, timestamp=ahora - timedelta(hours=1))
        MedicionAmbiente.objects.create(cultivo=cls.cultivo, temperatura_c=24, humedad_relativa=60, timestamp=ahora - timedelta(days=20))

    def setUp(self):
        self.client.force_login(self.owner)

    def test_cada_lectura_se_juzga_con_su_etapa(self):
        from .services.vpd import mapa_vpd
        datos = mapa_vpd(self.cultivo, "7d")
        self.assertEqual([l["estado"] for l in datos["lecturas"]], ["alto", "ideal"])
        self.assertEqual(datos["en_rango"], 50)
        self.assertEqual(len(mapa_vpd(self.cultivo, "ciclo")["lecturas"]), 3)

    def test_etapa_sin_ideal_de_vpd_no_juzga(self):
        from .services.vpd import mapa_vpd
        secado = next(e for e in mapa_vpd(self.cultivo)["etapas"] if e["clave"] == "secado")
        self.assertIsNone(secado["vpd"])

    def test_pantalla_y_enlace_desde_el_cultivo(self):
        url = reverse("growlog:cultivo_vpd", args=[self.cultivo.slug])
        self.assertContains(self.client.get(reverse("growlog:cultivo_detail", args=[self.cultivo.slug])), url)
        page = self.client.get(url + "?rango=cualquiera")
        self.assertEqual(page.context["datos"]["rango"], "7d")
        self.assertEqual(page.context["ultima_estado"], "ideal")
        self.assertContains(page, 'id="vpd-datos"')

    def test_lector_puede_ver_el_mapa(self):
        from .models import CultivoMiembro
        lector = User.objects.create_user("lector-vpd")
        CultivoMiembro.objects.create(cultivo=self.cultivo, usuario=lector, rol="lector")
        self.client.force_login(lector)
        self.assertEqual(self.client.get(reverse("growlog:cultivo_vpd", args=[self.cultivo.slug])).status_code, 200)


class ResumenCultivoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("resumen")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate() - timedelta(days=10),
                                             propietario=cls.owner)

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("growlog:cultivo_detail", args=[self.cultivo.slug])

    def test_dato_viejo_ofrece_medir(self):
        MedicionAmbiente.objects.create(cultivo=self.cultivo, temperatura_c=24, humedad_relativa=60,
                                        timestamp=timezone.now() - timedelta(hours=9))
        page = self.client.get(self.url)
        self.assertTrue(page.context["ambiente_viejo"])
        self.assertContains(page, "vital--viejo")
        self.assertContains(page, f"?cultivo={self.cultivo.pk}&kind=ambiente")
        MedicionAmbiente.objects.update(timestamp=timezone.now())
        page = self.client.get(self.url)
        self.assertFalse(page.context["ambiente_viejo"])
        self.assertNotContains(page, "vital--viejo")

    def test_vistas_del_cultivo_y_tareas_vencidas(self):
        Tarea.objects.create(cultivo=self.cultivo, titulo="Podar", fecha_objetivo=timezone.localdate() - timedelta(days=2))
        page = self.client.get(self.url)
        self.assertEqual(page.context["tareas_vencidas"], 1)
        self.assertContains(page, "1 vencida")
        for vista in ("cultivo_vpd", "cultivo_etapa"):
            self.assertContains(page, reverse(f"growlog:{vista}", args=[self.cultivo.slug]))
        # Hechas existe siempre: completar una tarea la agrega ahí por OOB.
        self.assertContains(page, 'id="tareas-done"')


class BitacoraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import CambioFotoperiodo, MedicionPlanta
        from .services.etapas import cambiar_etapa
        cls.owner = User.objects.create_user("bitacora")
        hoy = timezone.localdate()
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=hoy - timedelta(days=30), propietario=cls.owner)
        cambiar_etapa(cls.cultivo, "veg_temprano", cls.cultivo.fecha_inicio)
        CambioFotoperiodo.objects.create(cultivo=cls.cultivo, fotoperiodo="18/6", hora_lights_on=time(6), fecha_inicio=cls.cultivo.fecha_inicio)
        planta = Planta.objects.create(cultivo=cls.cultivo, apodo="Luna")
        MedicionPlanta.objects.create(planta=planta, fecha=hoy - timedelta(days=1), altura_cm=30)
        ahora = timezone.now()
        for i in range(60):
            MedicionAmbiente.objects.create(cultivo=cls.cultivo, temperatura_c=24, humedad_relativa=60, timestamp=ahora - timedelta(hours=3 * i))

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("growlog:timeline", args=[self.cultivo.slug])

    def test_incluye_ciclo_y_plantas_y_cuenta_todo(self):
        from .services.bitacora import bitacora
        datos = bitacora(self.cultivo, por_pagina=500)
        tipos = {r["tipo"] for r in datos["registros"]}
        self.assertTrue({"medicion", "etapa", "fotoperiodo", "planta"} <= tipos)
        self.assertEqual(datos["total"], 63)
        self.assertEqual({f["clave"]: f["cuenta"] for f in datos["filtros"]}["ciclo"], 2)
        self.assertEqual([r["tipo"] for r in bitacora(self.cultivo, "planta")["registros"]], ["planta"])

    def test_paginas_sin_repetir_ni_perder(self):
        from .services.bitacora import bitacora
        primera = bitacora(self.cultivo)
        self.assertTrue(primera["hay_mas"])
        segunda = bitacora(self.cultivo, desde=primera["siguiente"], dia_anterior=primera["ultimo_dia"])
        pks = [(r["tipo"], r["obj"].pk) for r in primera["registros"] + segunda["registros"]]
        self.assertEqual(len(pks), 63)
        self.assertEqual(len(set(pks)), 63)
        self.assertFalse(segunda["hay_mas"])
        # El separador de día no se repite si la página siguiente sigue en el mismo día.
        self.assertEqual(segunda["registros"][0]["nuevo_dia"], segunda["registros"][0]["dia"] != primera["ultimo_dia"])

    def test_ver_mas_devuelve_solo_filas(self):
        page = self.client.get(self.url)
        self.assertContains(page, "Ver más")
        mas = self.client.get(self.url + "?desde=50", HTTP_HX_REQUEST="true")
        self.assertNotContains(mas, "<h1")
        self.assertContains(mas, "nc-reg")
        self.assertEqual(self.client.get(self.url + "?desde=x&dia=2026-99-99").status_code, 200)
