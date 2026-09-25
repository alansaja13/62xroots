"""Login y logout."""
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import PushSubscription


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("growlog:dashboard")
    error = None
    if request.method == "POST":
        ip = _get_client_ip(request)
        cache_key = f"login_failures_{ip}"
        failures = cache.get(cache_key, 0)
        max_attempts = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
        lockout_secs = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 3600)

        if failures >= max_attempts:
            error = "Demasiados intentos fallidos. Esperá 1 hora antes de reintentar."
        else:
            user = authenticate(
                request,
                username=request.POST.get("username"),
                password=request.POST.get("password"),
            )
            if user:
                cache.delete(cache_key)
                login(request, user)
                # L-3: "recordar sesión" funcional
                if not request.POST.get("remember"):
                    request.session.set_expiry(0)
                # H-3: validar next para evitar open redirect
                next_url = request.GET.get("next", "")
                if next_url and url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    return redirect(next_url)
                return redirect("growlog:dashboard")
            else:
                cache.set(cache_key, failures + 1, timeout=lockout_secs)
                error = "Usuario o contraseña incorrectos."
    return render(request, "growlog/login.html", {"error": error})


@require_POST
def logout_view(request):
    # Revocar solo la suscripción de este navegador, conservando otros dispositivos.
    endpoint = request.POST.get("push_endpoint") or request.session.get("push_endpoint")
    if endpoint and request.user.is_authenticated:
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    logout(request)
    return redirect("growlog:login")


# ---------------------------------------------------------------------------
