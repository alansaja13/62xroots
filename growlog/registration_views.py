"""Shell pública y endpoints de sesión para el registro offline."""
import json

from django.conf import settings
from django.db import OperationalError
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from .models import ClaveRegistroLocal, Evento, MedicionEC, Nutriente, Tarea
from .permissions import cultivos_visibles
from .services.registro import RegistroError, recibir_registro

OFFLINE_COOKIE = "growlog_offline"


def offline_key(user):
    # Clave de cifrado local, nunca una credencial aceptada por el servidor.
    # Se recupera solo tras autenticarse; no depende de claves de despliegue.
    return ClaveRegistroLocal.objects.get_or_create(usuario=user)[0].clave


def error(message, status):
    response = JsonResponse({"ok": False, "error": message}, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def registrar(request):
    # Sin request/contexto de usuario: es seguro precargar este documento público.
    response = HttpResponse(render_to_string("growlog/registrar.html"))
    response["Cache-Control"] = "public, max-age=0, must-revalidate"
    return response


@require_GET
def contexto(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return error("Iniciá sesión para sincronizar tus registros.", 401)
    cultivos = cultivos_visibles(request.user, editar=True).prefetch_related("plantas")
    data = {
        "usuario": {"id": request.user.pk, "nombre": request.user.username},
        "desbloqueo": {
            "clave": offline_key(request.user),
            "max_age": None if request.session.get_expire_at_browser_close() else request.session.get_expiry_age(),
            "secure": settings.SESSION_COOKIE_SECURE,
        },
        "csrf": get_token(request),
        "cultivos": [{"id": c.pk, "slug": c.slug, "nombre": c.nombre, "archivado": c.archivado,
                      "plantas": [{"id": p.pk, "nombre": p.apodo} for p in c.plantas.all() if not p.archivado and p.estado == "activa"]} for c in cultivos],
        "nutrientes": list(Nutriente.objects.values("id", "nombre", "marca")),
        "opciones": {"eventos": Evento.TIPO_CHOICES, "ec": MedicionEC.TIPO_CHOICES,
                     "categorias": Tarea.CATEGORIA_CHOICES, "prioridades": Tarea.PRIORIDAD_CHOICES},
    }
    response = JsonResponse(data)
    response["Cache-Control"] = "private, no-store"
    # El cliente instala el desbloqueo solo si sigue en la misma sesión al
    # recibir la respuesta. Un Set-Cookie tardío podría reabrir una cuenta
    # después de que otra pestaña cerró sesión.
    return response


@require_POST
def sincronizar(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return error("Iniciá sesión para sincronizar tus registros.", 401)
    if request.headers.get("X-Registro-Cuenta") != str(request.user.pk):
        return error("Cambió la cuenta activa. Abrí Registrar de nuevo antes de sincronizar.", 409)
    if len(request.body) > 65536:
        return error("El registro supera el tamaño permitido.", 413)
    try:
        def reject_constant(value):
            raise ValueError("Número no finito")
        payload = json.loads(request.body, parse_constant=reject_constant)
        result, created = recibir_registro(request.user, payload)
    except (ValueError, UnicodeDecodeError):
        return error("El registro no contiene JSON válido.", 400)
    except RegistroError as exc:
        return JsonResponse({"ok": False, "error": exc.mensaje, "campos": exc.campos}, status=exc.status)
    except OperationalError:
        response = error("No pudimos confirmar el guardado. El pendiente se conserva para reintentar.", 503)
        response["Retry-After"] = "5"
        return response
    return JsonResponse({"ok": True, "data": result, "repetido": not created}, status=201 if created else 200)
