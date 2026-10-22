import json

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

    def test_service_worker_solo_maneja_push_y_limpia_caches_viejas(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        js = response.content.decode()
        self.assertNotRegex(js, r"\{\{|\{%")
        self.assertIn("addEventListener('push'", js)
        self.assertIn("caches.delete", js)
        self.assertNotIn("addEventListener('fetch'", js)


class PwaHeadTests(TestCase):
    """Safari y Chrome solo leen la página desde la que se instala la app."""

    def test_paginas_independientes_son_instalables(self):
        from django.contrib.auth.models import User
        paginas = {"/login/": self.client.get("/login/")}
        self.client.force_login(User.objects.create_user("pwa"))
        paginas["/ (base)"] = self.client.get("/")
        paginas["/registrar/"] = self.client.get("/registrar/")
        for nombre, response in paginas.items():
            with self.subTest(pagina=nombre):
                for fragmento in ('rel="manifest"', 'rel="apple-touch-icon"', 'name="apple-mobile-web-app-capable"',
                                  "serviceWorker.register('/sw.js'"):
                    self.assertContains(response, fragmento, count=1)

    def test_login_recuerda_la_sesion_por_defecto(self):
        self.assertContains(self.client.get("/login/"), 'name="remember" checked')

    def test_ningun_comentario_de_template_se_filtra_al_html(self):
        # {# #} de Django es de una sola línea; uno multilínea se muestra como texto.
        from django.contrib.auth.models import User
        self.assertNotContains(self.client.get("/login/"), "{#")
        self.client.force_login(User.objects.create_user("comentarios"))
        for url in ("/", "/registrar/"):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "{#")
