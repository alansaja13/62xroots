from django.contrib.admin import AdminSite


class MaintenanceAdminSite(AdminSite):
    """Administración global reservada al mantenimiento de la instalación."""

    def has_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser and request.user.is_staff)
