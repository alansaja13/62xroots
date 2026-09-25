from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class MaintenanceAdminConfig(AdminConfig):
    default_site = "growlog.admin_site.MaintenanceAdminSite"


class GrowlogConfig(AppConfig):
    name = 'growlog'
