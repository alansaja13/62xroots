from django.utils.cache import patch_cache_control, patch_vary_headers
from .registration_views import OFFLINE_COOKIE


class PrivateBitacoraMiddleware:
    """Las páginas privadas no son el almacén offline de la PWA."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        identity = request.COOKIES.get(OFFLINE_COOKIE, "")
        if request.path == "/logout/" and request.method == "POST" or (
            request.user.is_authenticated and identity
            and not identity.startswith(f"{request.user.pk}.")
            and OFFLINE_COOKIE not in response.cookies
        ):
            response.delete_cookie(OFFLINE_COOKIE, path="/", samesite="Lax")
        if (
            request.user.is_authenticated
            or request.path.startswith(("/api/", "/media/", "/login/", "/logout/", "/registrar/"))
        ) and request.path not in {"/sw.js", "/manifest.json", "/registrar/"}:
            patch_cache_control(response, private=True, no_store=True)
            patch_vary_headers(response, ["Cookie"])
        return response
