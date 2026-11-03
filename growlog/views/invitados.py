"""Compartir cultivos: links de invitación de un solo uso y accesos de cuentas que ya existen."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import CompartirCultivoForm, CuentaInvitadoForm
from ..models import CultivoMiembro, Invitacion


def _sin_cache(response):
    response["Cache-Control"] = "no-store, private"
    return response


def _panel_invitados(request, *, form=None, status=200):
    nueva = request.GET.get("nueva")
    pendientes = (Invitacion.objects.filter(creada_por=request.user, usada_en__isnull=True, vence__gt=timezone.now())
                  .select_related("cultivo"))
    return _sin_cache(render(request, "growlog/invitados.html", {
        "form": form if form is not None else CompartirCultivoForm(usuario=request.user),
        "invitados": CultivoMiembro.objects.filter(cultivo__propietario=request.user)
            .select_related("cultivo", "usuario").order_by("cultivo__nombre", "usuario__username"),
        "pendientes": pendientes,
        "nueva": next((i for i in pendientes if str(i.pk) == nueva), None),
        "roles": CultivoMiembro.ROLES,
    }, status=status))


@login_required
def invitados_panel(request):
    return _panel_invitados(request)


@login_required
@require_POST
def invitado_crear(request):
    """Sin usuario arma un link de invitación; con usuario da acceso a esa cuenta."""
    form = CompartirCultivoForm(request.POST, usuario=request.user)
    if not form.is_valid():
        return _panel_invitados(request, form=form, status=400)
    cultivo, rol, username = form.cleaned_data["cultivo"], form.cleaned_data["rol"], form.cleaned_data["usuario"]
    if not username:
        invitacion = Invitacion.objects.create(cultivo=cultivo, rol=rol, creada_por=request.user)
        return redirect(f"{reverse('growlog:invitados_panel')}?nueva={invitacion.pk}#link")
    usuario = User.objects.filter(username=username, is_active=True).first()
    if usuario is None or usuario.pk == request.user.pk:
        form.add_error("usuario", "No hay otra cuenta activa con ese usuario.")
        return _panel_invitados(request, form=form, status=400)
    CultivoMiembro.objects.update_or_create(cultivo=cultivo, usuario=usuario, defaults={"rol": rol})
    messages.success(request, f"Acceso actualizado para {usuario.username} en {cultivo.nombre}.")
    return redirect("growlog:invitados_panel")


@login_required
@require_POST
def invitacion_revocar(request, pk):
    get_object_or_404(Invitacion, pk=pk, creada_por=request.user, usada_en__isnull=True).delete()
    messages.success(request, "Link anulado. Ya no sirve para entrar.")
    return redirect("growlog:invitados_panel")


def invitacion_aceptar(request, token):
    """El invitado abre el link: con sesión se suma; sin sesión crea su cuenta o entra con la que tiene."""
    invitacion = Invitacion.objects.select_related("cultivo", "creada_por").filter(token=token).first()
    if invitacion is None or not invitacion.vigente:
        return _sin_cache(render(request, "growlog/invitacion.html", {"invitacion": invitacion, "invalida": True}, status=410))
    cultivo = invitacion.cultivo
    form = None
    if request.user.is_authenticated:
        if cultivo.propietario_id == request.user.pk:
            messages.info(request, "Este cultivo ya es tuyo.")
            return redirect("growlog:cultivo_detail", cultivo.slug)
        if request.method == "POST":
            _usar(invitacion, request.user)
            messages.success(request, f"Listo, ya estás en {cultivo.nombre}.")
            return redirect("growlog:cultivo_detail", cultivo.slug)
    else:
        form = CuentaInvitadoForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            with transaction.atomic():
                usuario = form.save()
                _usar(invitacion, usuario)
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Listo, ya tenés tu cuenta y estás en {cultivo.nombre}.")
            return redirect("growlog:cultivo_detail", cultivo.slug)
    return _sin_cache(render(request, "growlog/invitacion.html", {"invitacion": invitacion, "form": form}))


@transaction.atomic
def _usar(invitacion, usuario):
    # Si ya era miembro con más permiso, el link no lo baja.
    miembro, creado = CultivoMiembro.objects.get_or_create(cultivo=invitacion.cultivo, usuario=usuario,
                                                          defaults={"rol": invitacion.rol})
    if not creado and invitacion.rol == "editor" and miembro.rol != "editor":
        miembro.rol = "editor"
        miembro.save(update_fields=["rol"])
    invitacion.usada_por = usuario
    invitacion.usada_en = timezone.now()
    invitacion.save(update_fields=["usada_por", "usada_en"])


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
