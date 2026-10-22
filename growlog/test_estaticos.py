"""Con el storage de manifest, un {% static %} a un archivo inexistente rompe la página."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

STATIC_TAG = re.compile(r"""\{%\s*static\s+['"]([^'"]+)['"]\s*%\}""")


class ReferenciasEstaticasTests(SimpleTestCase):
    def test_todo_static_de_las_plantillas_existe(self):
        faltantes = []
        for carpeta in settings.TEMPLATES[0]["DIRS"]:
            for plantilla in Path(carpeta).rglob("*.html"):
                for ruta in STATIC_TAG.findall(plantilla.read_text(encoding="utf-8")):
                    if not finders.find(ruta):
                        faltantes.append(f"{plantilla.name}: {ruta}")
        self.assertEqual(faltantes, [])
