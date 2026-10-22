from django.utils.cache import patch_cache_control, patch_vary_headers


class PrivateBitacoraMiddleware:
    """Las páginas privadas no quedan en cachés del navegador ni compartidas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.user.is_authenticated
            or request.path.startswith(("/api/", "/media/", "/login/", "/logout/"))
        ) and request.path not in {"/sw.js", "/manifest.json"}:
            patch_cache_control(response, private=True, no_store=True)
            patch_vary_headers(response, ["Cookie"])
        return response


class CultivoRecienteMiddleware:
    """Recuerda el último cultivo abierto para que Registrar lo proponga primero."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        cultivo = getattr(request, "cultivo_actual", None)
        if cultivo is not None and request.session.get("cultivo_reciente") != cultivo.pk:
            request.session["cultivo_reciente"] = cultivo.pk
        return response
