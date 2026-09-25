"""Compartir cultivos con otras cuentas."""
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import CompartirCultivoForm
from ..models import CultivoMiembro


_ADJETIVOS = ["verde", "oscuro", "suave", "fresco", "lento", "rapido", "alto", "bajo",
               "denso", "claro", "largo", "nuevo", "viejo", "sabio", "fuerte", "fino"]
_SUSTANTIVOS = ["arbol", "hoja", "raiz", "flor", "tallo", "brote", "fruto", "campo",
                "tronco", "limon", "roca", "viento", "bosque", "campo", "lirio", "cedro"]


def _panel_invitados(request, *, form=None, nuevo=None, status=200):
    response = render(request, "growlog/invitados.html", {
        "form": form if form is not None else CompartirCultivoForm(usuario=request.user),
        "invitados": CultivoMiembro.objects.filter(cultivo__propietario=request.user)
            .select_related("cultivo", "usuario").order_by("cultivo__nombre", "usuario__username"),
        "nuevo": nuevo,
        "roles": CultivoMiembro.ROLES,
    }, status=status)
    response["Cache-Control"] = "no-store, private"
    return response


@login_required
def invitados_panel(request):
    return _panel_invitados(request)


@login_required
@require_POST
def invitado_crear(request):
    form = CompartirCultivoForm(request.POST, usuario=request.user)
    if not form.is_valid():
        return _panel_invitados(request, form=form, status=400)
    cultivo = form.cleaned_data["cultivo"]
    username = form.cleaned_data["usuario"]
    usuario = None
    nuevo = None
    if username:
        usuario = User.objects.filter(username=username, is_active=True).first()
        if usuario is None or usuario.pk == request.user.pk:
            form.add_error("usuario", "Elegí otra cuenta activa existente.")
            return _panel_invitados(request, form=form, status=400)
    with transaction.atomic():
        if usuario is None:
            # Un sufijo aleatorio evita colisiones sin exponer otros usuarios.
            username = f"{secrets.choice(_ADJETIVOS)}{secrets.choice(_SUSTANTIVOS)}{secrets.token_hex(4)}"
            password = secrets.token_urlsafe(16)
            usuario = User.objects.create_user(username=username, password=password)
            nuevo = {"username": username, "password": password}
        CultivoMiembro.objects.update_or_create(
            cultivo=cultivo, usuario=usuario, defaults={"rol": form.cleaned_data["rol"]},
        )
    messages.success(request, f"Acceso actualizado para {usuario.username} en {cultivo.nombre}.")
    if nuevo:
        return _panel_invitados(request, nuevo=nuevo)
    return redirect("growlog:invitados_panel")


@login_required
@require_POST
def invitado_rol(request, pk):
    miembro = get_object_or_404(CultivoMiembro, pk=pk, cultivo__propietario=request.user)
    rol = request.POST.get("rol")
    if rol not in dict(CultivoMiembro.ROLES):
        return HttpResponse("Permiso inválido", status=400)
    miembro.rol = rol
    miembro.save(update_fields=["rol"])
    messages.success(request, "Permiso actualizado.")
    return redirect("growlog:invitados_panel")


@login_required
@require_POST
def invitado_eliminar(request, pk):
    miembro = get_object_or_404(CultivoMiembro, pk=pk, cultivo__propietario=request.user)
    miembro.delete()
    messages.success(request, "Acceso revocado. La cuenta y los registros se conservan.")
    return redirect("growlog:invitados_panel")


# ---------------------------------------------------------------------------
