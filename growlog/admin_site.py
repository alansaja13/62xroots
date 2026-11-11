from django.contrib.admin import AdminSite
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse


class MaintenanceAdminSite(AdminSite):
    """Administración global reservada al mantenimiento de la instalación."""

    def has_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser and request.user.is_staff)

    def login(self, request, extra_context=None):
        # Un solo formulario de ingreso: el de la app, que tiene el límite de
        # intentos. El del admin permitía probar contraseñas sin freno.
        inicio = reverse("admin:index", current_app=self.name)
        if self.has_permission(request):
            return redirect(inicio)
        return redirect_to_login(request.GET.get("next") or inicio)
