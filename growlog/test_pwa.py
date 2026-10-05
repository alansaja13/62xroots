import json
import re

from django.test import TestCase


class PwaTests(TestCase):
    def test_manifest_instalable_con_colores_de_la_app(self):
        response = self.client.get("/manifest.json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/manifest+json"))
        data = json.loads(response.content)
        self.assertEqual(data["id"], "/")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["theme_color"], data["background_color"])
        sizes = {(i["sizes"], i["purpose"]) for i in data["icons"]}
        self.assertIn(("512x512", "maskable"), sizes)
        self.assertIn(("192x192", "any"), sizes)
        self.assertIn("/registrar/", [s["url"] for s in data["shortcuts"]])

    def test_service_worker_inyecta_assets_de_registrar_y_version(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        js = response.content.decode()
        self.assertNotRegex(js, r"\{\{|\{%")
        self.assertRegex(js, r"const VERSION = '[0-9a-f]{10}';")
        assets = json.loads(re.search(r"const OFFLINE_ASSETS = (\[.*?\]);", js).group(1))
        self.assertEqual(assets[0], "/registrar/")
        self.assertIn("/static/growlog/verde.css", assets)
        self.assertIn("/static/growlog/registrar.js", assets)

    def test_registrar_referencia_los_mismos_assets_que_precarga_el_sw(self):
        js = self.client.get("/sw.js").content.decode()
        assets = json.loads(re.search(r"const OFFLINE_ASSETS = (\[.*?\]);", js).group(1))
        html = self.client.get("/registrar/").content.decode()
        for asset in assets[1:]:
            self.assertIn(f'"{asset}"', html)

    def test_registrar_no_promete_un_registro_clasico_que_ya_no_existe(self):
        # El alta de riego/evento/EC/tarea vive solo en Registrar (ver test_pantallas_clasicas_de_alta_ya_no_existen).
        html = self.client.get("/registrar/").content.decode()
        self.assertNotIn("classic-link", html)
        self.assertNotIn("clásico", html)


class PwaHeadTests(TestCase):
    """Safari y Chrome solo leen la página desde la que se instala la app."""

    def test_paginas_independientes_son_instalables(self):
        from django.contrib.auth.models import User
        paginas = {"/login/": self.client.get("/login/"), "/registrar/": self.client.get("/registrar/")}
        self.client.force_login(User.objects.create_user("pwa"))
        paginas["/ (base)"] = self.client.get("/")
        for nombre, response in paginas.items():
            with self.subTest(pagina=nombre):
                for fragmento in ('rel="manifest"', 'rel="apple-touch-icon"', 'name="apple-mobile-web-app-capable"',
                                  "serviceWorker.register('/sw.js'"):
                    self.assertContains(response, fragmento, count=1)

    def test_login_recuerda_la_sesion_por_defecto(self):
        self.assertContains(self.client.get("/login/"), 'name="remember" checked')

    def test_ningun_comentario_de_template_se_filtra_al_html(self):
        # {# #} de Django es de una sola línea; uno multilínea se muestra como texto.
        for url in ("/login/", "/registrar/"):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "{#")
