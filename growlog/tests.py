import hashlib
import secrets

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from .models import APIToken, Cultivo, Planta


class APIAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(self.raw_token.encode()).hexdigest()
        self.token = APIToken.objects.create(user=self.user, token_hash=token_hash)
        self.cultivo = Cultivo.objects.create(
            nombre='Test Cultivo',
            fecha_inicio=timezone.localdate(),
            estado='vegetativo',
            creado_por=self.user,
        )

    def _auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.raw_token}'}

    # ── Auth ──────────────────────────────────────────────────────────────────

    def test_no_token_returns_401(self):
        r = self.client.get('/api/v1/cultivos/')
        self.assertEqual(r.status_code, 401)
        self.assertFalse(r.json()['ok'])

    def test_missing_bearer_prefix_returns_401(self):
        r = self.client.get('/api/v1/cultivos/', HTTP_AUTHORIZATION=self.raw_token)
        self.assertEqual(r.status_code, 401)

    def test_invalid_token_returns_401(self):
        r = self.client.get('/api/v1/cultivos/', HTTP_AUTHORIZATION='Bearer token-invalido')
        self.assertEqual(r.status_code, 401)
        self.assertFalse(r.json()['ok'])

    def test_valid_token_returns_200(self):
        r = self.client.get('/api/v1/cultivos/', **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])

    # ── Scoping H-2 ───────────────────────────────────────────────────────────

    def test_cultivo_scoped_a_usuario(self):
        otro = User.objects.create_user('otro', password='testpass123')
        cultivo_ajeno = Cultivo.objects.create(
            nombre='Ajeno', fecha_inicio=timezone.localdate(),
            estado='vegetativo', creado_por=otro,
        )
        r = self.client.get(f'/api/v1/cultivos/{cultivo_ajeno.slug}/', **self._auth())
        self.assertEqual(r.status_code, 404)

    def test_cultivos_list_solo_propios(self):
        otro = User.objects.create_user('otro2', password='testpass123')
        Cultivo.objects.create(
            nombre='Ajeno2', fecha_inicio=timezone.localdate(),
            estado='vegetativo', creado_por=otro,
        )
        r = self.client.get('/api/v1/cultivos/', **self._auth())
        data = r.json()['data']
        slugs = [c['slug'] for c in data]
        self.assertIn(self.cultivo.slug, slugs)
        self.assertNotIn('ajeno2', slugs)

    # ── Response shape ────────────────────────────────────────────────────────

    def test_cultivos_list_shape(self):
        r = self.client.get('/api/v1/cultivos/', **self._auth())
        data = r.json()['data']
        self.assertIsInstance(data, list)
        item = data[0]
        for key in ('id', 'slug', 'nombre', 'estado', 'fecha_inicio', 'dias_desde_inicio',
                    'lampara_watts_reales', 'sustrato', 'carpa_dimensiones'):
            self.assertIn(key, item)

    def test_cultivo_detail_shape(self):
        r = self.client.get(f'/api/v1/cultivos/{self.cultivo.slug}/', **self._auth())
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        for key in ('plantas', 'ultimos_riegos', 'ultimas_mediciones',
                    'ultimos_eventos', 'tareas_pendientes', 'notas'):
            self.assertIn(key, data)

    def test_cultivo_not_found_returns_404(self):
        r = self.client.get('/api/v1/cultivos/slug-inexistente/', **self._auth())
        self.assertEqual(r.status_code, 404)
        body = r.json()
        self.assertFalse(body['ok'])
        self.assertIn('error', body)

    def test_tareas_completada_filter(self):
        from .models import Tarea
        Tarea.objects.create(cultivo=self.cultivo, titulo='Pendiente', completada=False)
        Tarea.objects.create(cultivo=self.cultivo, titulo='Hecha', completada=True)

        r = self.client.get(
            f'/api/v1/cultivos/{self.cultivo.slug}/tareas/?completada=false', **self._auth()
        )
        data = r.json()['data']
        self.assertTrue(all(not t['completada'] for t in data))

    def test_planta_detail(self):
        planta = Planta.objects.create(
            cultivo=self.cultivo, apodo='P1', strain='OG Kush', estado='activa'
        )
        r = self.client.get(f'/api/v1/plantas/{planta.uuid}/', **self._auth())
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        self.assertEqual(data['apodo'], 'P1')
        self.assertIn('uuid', data)
        self.assertIn('mediciones', data)
        self.assertIn('cultivo', data)
        self.assertIn('slug', data['cultivo'])

    def test_planta_ajena_returns_404(self):
        otro = User.objects.create_user('otro3', password='testpass123')
        cultivo_ajeno = Cultivo.objects.create(
            nombre='Ajeno3', fecha_inicio=timezone.localdate(),
            estado='vegetativo', creado_por=otro,
        )
        planta_ajena = Planta.objects.create(
            cultivo=cultivo_ajeno, apodo='Extraña', estado='activa'
        )
        r = self.client.get(f'/api/v1/plantas/{planta_ajena.uuid}/', **self._auth())
        self.assertEqual(r.status_code, 404)
