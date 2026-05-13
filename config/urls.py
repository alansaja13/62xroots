"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from growlog.views import pwa_manifest, pwa_service_worker

handler400 = 'growlog.views.error_400'
handler403 = 'growlog.views.error_403'
handler404 = 'growlog.views.error_404'
handler500 = 'growlog.views.error_500'

urlpatterns = [
    path("admin/", admin.site.urls),
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "growlog/logo.png", permanent=True)),
    path("manifest.json", pwa_manifest),
    path("sw.js", pwa_service_worker),
    path("", include("growlog.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
