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
