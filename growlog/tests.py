import hashlib
import secrets
import zoneinfo
from datetime import datetime, time, date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    APIToken, CambioFotoperiodo, CanopySnapshot, ColaPosicion, Cultivo,
    Nutriente, NutrienteAplicado, Planta, Riego,
)
from .utils import calcular_luz_estado, get_cambio_fotoperiodo_activo, get_flip_a_flora

ART = zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires")


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


class CalcularLuzEstadoTests(TestCase):
    """Tests for calcular_luz_estado: lights-on 17:00, fotoperiodo 18/6 (off at 11:00)."""

    def _ts(self, hour, minute=0):
        return datetime(2026, 5, 13, hour, minute, tzinfo=ART)

    def test_during_on_window(self):
        self.assertEqual(calcular_luz_estado(self._ts(18), time(17, 0), "18/6"), "on")

    def test_during_off_window(self):
        self.assertEqual(calcular_luz_estado(self._ts(12), time(17, 0), "18/6"), "off")

    def test_past_midnight_on_window(self):
        self.assertEqual(calcular_luz_estado(self._ts(2), time(17, 0), "18/6"), "on")

    def test_boundary_lights_off(self):
        # 11:00 is exactly when lights turn off — should be "off"
        self.assertEqual(calcular_luz_estado(self._ts(11), time(17, 0), "18/6"), "off")

    def test_boundary_lights_on(self):
        # 17:00 is exactly when lights turn on — should be "on"
        self.assertEqual(calcular_luz_estado(self._ts(17), time(17, 0), "18/6"), "on")


class GetCambioFotoperiodoActivoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('fotouser', password='pass')
        self.cultivo = Cultivo.objects.create(
            nombre='Foto Test', fecha_inicio=date(2026, 1, 1),
            estado='vegetativo', creado_por=self.user,
        )
        self.veg = CambioFotoperiodo.objects.create(
            cultivo=self.cultivo,
            fotoperiodo='18/6',
            hora_lights_on=time(17, 0),
            fecha_inicio=date(2026, 1, 1),
        )
        self.flora = CambioFotoperiodo.objects.create(
            cultivo=self.cultivo,
            fotoperiodo='12/12',
            hora_lights_on=time(18, 0),
            fecha_inicio=date(2026, 3, 1),
        )

    def test_before_flip_returns_veg(self):
        ts = datetime(2026, 2, 15, 12, 0, tzinfo=ART)
        result = get_cambio_fotoperiodo_activo(self.cultivo, ts)
        self.assertEqual(result, self.veg)

    def test_after_flip_returns_flora(self):
        ts = datetime(2026, 4, 1, 12, 0, tzinfo=ART)
        result = get_cambio_fotoperiodo_activo(self.cultivo, ts)
        self.assertEqual(result, self.flora)

    def test_on_flip_date_returns_flora(self):
        ts = datetime(2026, 3, 1, 0, 0, tzinfo=ART)
        result = get_cambio_fotoperiodo_activo(self.cultivo, ts)
        self.assertEqual(result, self.flora)


class GetFlipAFloraTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('flipuser', password='pass')
        self.cultivo = Cultivo.objects.create(
            nombre='Flip Test', fecha_inicio=date(2026, 1, 1),
            estado='floracion', creado_por=self.user,
        )

    def test_sin_cambios_devuelve_none(self):
        self.assertIsNone(get_flip_a_flora(self.cultivo))

    def test_solo_veg_devuelve_none(self):
        CambioFotoperiodo.objects.create(
            cultivo=self.cultivo, fotoperiodo='18/6',
            hora_lights_on=time(17, 0), fecha_inicio=date(2026, 1, 1),
        )
        self.assertIsNone(get_flip_a_flora(self.cultivo))

    def test_devuelve_primer_cambio_a_12h_o_menos(self):
        CambioFotoperiodo.objects.create(
            cultivo=self.cultivo, fotoperiodo='18/6',
            hora_lights_on=time(17, 0), fecha_inicio=date(2026, 1, 1),
        )
        flip = CambioFotoperiodo.objects.create(
            cultivo=self.cultivo, fotoperiodo='12/12',
            hora_lights_on=time(18, 0), fecha_inicio=date(2026, 3, 1),
        )
        self.assertEqual(get_flip_a_flora(self.cultivo), flip)


class ReporteViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user('staffuser', password='pass', is_staff=True)
        self.client.login(username='staffuser', password='pass')
        self.cultivo = Cultivo.objects.create(
            nombre='Reporte Test', fecha_inicio=date(2026, 1, 1),
            estado='floracion', lampara_watts_reales=300, creado_por=self.staff,
        )
        self.planta = Planta.objects.create(
            cultivo=self.cultivo, apodo='R1', yield_estimado_g=80, yield_real_g=65,
        )
        nutriente = Nutriente.objects.create(nombre='Grow', marca='BioBizz')
        riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=3000, ph_agua=6.2)
        NutrienteAplicado.objects.create(riego=riego, nutriente=nutriente, dosis_g_por_litro=2)

    def test_reporte_renderiza(self):
        r = self.client.get(f'/cultivo/{self.cultivo.slug}/reporte/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Reporte Test')
        self.assertContains(r, '65 g')  # yield real

    def test_reporte_g_por_watt(self):
        r = self.client.get(f'/cultivo/{self.cultivo.slug}/reporte/')
        # 65 g / 300 W = 0.22
        self.assertEqual(r.context['g_por_watt'], 0.22)

    def test_export_csv(self):
        r = self.client.get(f'/cultivo/{self.cultivo.slug}/reporte/?export=csv')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r['Content-Type'])
        body = r.content.decode('utf-8')
        self.assertIn('riego', body)
        self.assertIn('3000', body)

    def test_requiere_login(self):
        self.client.logout()
        r = self.client.get(f'/cultivo/{self.cultivo.slug}/reporte/')
        self.assertEqual(r.status_code, 302)

    def test_cultivo_detail_muestra_dia_flora(self):
        CambioFotoperiodo.objects.create(
            cultivo=self.cultivo, fotoperiodo='12/12',
            hora_lights_on=time(18, 0),
            fecha_inicio=timezone.localdate() - timezone.timedelta(days=9),
        )
        r = self.client.get(f'/cultivo/{self.cultivo.slug}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['dia_flora'], 10)

    def test_cultivo_detail_dias_sin_riego(self):
        r = self.client.get(f'/cultivo/{self.cultivo.slug}/')
        self.assertEqual(r.context['dias_sin_riego'], 0)


class CanopyAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('canopy_user', password='testpass123')
        self.raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(self.raw_token.encode()).hexdigest()
        APIToken.objects.create(user=self.user, token_hash=token_hash)
        self.cultivo = Cultivo.objects.create(
            nombre='Canopy Test',
            fecha_inicio=timezone.localdate(),
            estado='floracion',
            lampara_watts_reales=314,
            creado_por=self.user,
        )
        self.planta = Planta.objects.create(
            cultivo=self.cultivo,
            apodo='FG1',
            posicion_tent='centro',
            creado_por=self.user,
        )

    def _auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.raw_token}'}

    def _post_json(self, url, data):
        import json
        return self.client.generic(
            'POST', url, json.dumps(data),
            content_type='application/json',
            **self._auth(),
        )

    def test_get_canopy_sin_snapshot_devuelve_null(self):
        r = self.client.get(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/', **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])
        self.assertIsNone(r.json()['data'])

    def test_post_canopy_crea_snapshot(self):
        payload = {
            'scrog_fill_pct': 40,
            'notas': 'Test snapshot',
            'colas': [
                {'planta_uuid': str(self.planta.uuid), 'indice': 0, 'x': 0.5, 'y': 0.45},
                {'planta_uuid': str(self.planta.uuid), 'indice': 1, 'x': 0.5, 'y': 0.55},
            ],
        }
        r = self._post_json(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/', payload)
        self.assertEqual(r.status_code, 201)
        data = r.json()['data']
        self.assertEqual(data['scrog_fill_pct'], 40)
        self.assertEqual(len(data['plantas']), 1)
        self.assertEqual(len(data['plantas'][0]['colas']), 2)
        self.assertEqual(CanopySnapshot.objects.count(), 1)
        self.assertEqual(ColaPosicion.objects.count(), 2)

    def test_get_canopy_devuelve_ultimo_snapshot(self):
        snap = CanopySnapshot.objects.create(cultivo=self.cultivo, scrog_fill_pct=60)
        ColaPosicion.objects.create(snapshot=snap, planta=self.planta, indice=0, x=0.5, y=0.4)
        r = self.client.get(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/', **self._auth())
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        self.assertEqual(data['id'], snap.id)
        self.assertEqual(data['scrog_fill_pct'], 60)
        self.assertEqual(data['plantas'][0]['apodo'], 'FG1')

    def test_get_canopy_history(self):
        CanopySnapshot.objects.create(cultivo=self.cultivo, scrog_fill_pct=20)
        CanopySnapshot.objects.create(cultivo=self.cultivo, scrog_fill_pct=50)
        r = self.client.get(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/history/', **self._auth())
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        self.assertEqual(len(data), 2)

    def test_get_canopy_detail(self):
        snap = CanopySnapshot.objects.create(cultivo=self.cultivo, scrog_fill_pct=75, notas='detalle')
        r = self.client.get(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/{snap.id}/', **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['data']['notas'], 'detalle')

    def test_post_canopy_scrog_fuera_de_rango_devuelve_400(self):
        payload = {'scrog_fill_pct': 150, 'colas': []}
        r = self._post_json(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/', payload)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_post_canopy_coords_fuera_de_rango_devuelve_400(self):
        payload = {
            'scrog_fill_pct': 30,
            'colas': [{'planta_uuid': str(self.planta.uuid), 'indice': 0, 'x': 1.5, 'y': 0.5}],
        }
        r = self._post_json(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/', payload)
        self.assertEqual(r.status_code, 400)

    def test_post_canopy_uuid_invalido_devuelve_400(self):
        payload = {
            'scrog_fill_pct': 30,
            'colas': [{'planta_uuid': 'uuid-falso', 'indice': 0, 'x': 0.5, 'y': 0.5}],
        }
        r = self._post_json(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/', payload)
        self.assertEqual(r.status_code, 400)

    def test_centro_tent_coords_en_respuesta(self):
        snap = CanopySnapshot.objects.create(cultivo=self.cultivo, scrog_fill_pct=0)
        r = self.client.get(f'/api/v1/cultivos/{self.cultivo.slug}/canopy/{snap.id}/', **self._auth())
        planta_data = r.json()['data']['plantas'][0]
        self.assertEqual(planta_data['centro_tent'], {'x': 0.5, 'y': 0.5})
