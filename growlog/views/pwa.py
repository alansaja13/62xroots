"""PWA: manifest, service worker y suscripciones push."""
import hashlib
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.templatetags.static import static as static_url
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import PushSubscription


# ---------------------------------------------------------------------------
# Push notifications
# ---------------------------------------------------------------------------

@login_required
@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
        return JsonResponse({"error": "Suscripción inválida"}, status=400)
    endpoint = data.get("endpoint")
    keys = data["keys"]
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not all(isinstance(value, str) and value for value in (endpoint, p256dh, auth)):
        return JsonResponse({"error": "Datos de suscripción incompletos"}, status=400)

    sub, created = PushSubscription.objects.get_or_create(
        endpoint=endpoint, defaults={"user": request.user, "p256dh": p256dh, "auth": auth},
    )
    if sub.user_id != request.user.pk:
        return JsonResponse({"error": "Esta suscripción pertenece a otra cuenta"}, status=409)
    if not created:
        sub.p256dh, sub.auth = p256dh, auth
        sub.save(update_fields=["p256dh", "auth"])
    request.session["push_endpoint"] = endpoint
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    if not isinstance(data, dict) or not isinstance(data.get("endpoint"), str):
        return JsonResponse({"error": "Suscripción inválida"}, status=400)
    endpoint = data["endpoint"]
    if endpoint:
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# PWA — manifest + service worker
# ---------------------------------------------------------------------------

# Mismo fondo que la app (--bg en base.html): la splash de Android y la barra
# de estado no "saltan" de color al abrir.
THEME_COLOR = "#0e120c"


def pwa_manifest(request):
    def icon(name, size, purpose="any"):
        return {"src": static_url(f"growlog/icons/{name}"), "sizes": size, "type": "image/png", "purpose": purpose}

    data = {
        "id": "/",
        "name": "62×ROOTS GrowLog",
        "short_name": "62×ROOTS",
        "description": "Bitácora de cultivo indoor: riegos, ambiente, plantas y tareas.",
        "lang": "es-AR",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": THEME_COLOR,
        "theme_color": THEME_COLOR,
        "categories": ["productivity", "lifestyle"],
        "icons": [
            icon("icon-192x192.png", "192x192"),
            icon("icon-512x512.png", "512x512"),
            icon("maskable-192x192.png", "192x192", "maskable"),
            icon("maskable-512x512.png", "512x512", "maskable"),
        ],
        "shortcuts": [
            {"name": "Registrar", "short_name": "Registrar", "description": "Anotar ambiente, riego u observación, con o sin señal",
             "url": "/registrar/", "icons": [icon("shortcut-registrar-96x96.png", "96x96")]},
            {"name": "Hoy", "short_name": "Hoy", "description": "Pendientes y últimos registros",
             "url": "/", "icons": [icon("maskable-192x192.png", "192x192")]},
        ],
    }
    response = JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    response["Content-Type"] = "application/manifest+json; charset=utf-8"
    return response


# Lo mínimo para que Registrar abra sin señal. Solo contenido público.
OFFLINE_STATIC = (
    "growlog/verde.css", "growlog/registrar.css", "growlog/offline-store.js", "growlog/registrar-datos.js", "growlog/registrar.js",
    "growlog/icons/icon-96x96.png",
)


def pwa_service_worker(request):
    offline_url = reverse("growlog:registrar")
    assets = [offline_url, *(static_url(path) for path in OFFLINE_STATIC)]
    version = hashlib.sha256(json.dumps(assets).encode()).hexdigest()[:10]
    js = render_to_string("pwa/sw.js", {
        "version": version, "offline_url": offline_url, "offline_assets": json.dumps(assets),
    })
    response = HttpResponse(js, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
