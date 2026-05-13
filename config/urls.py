from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include, re_path
from django.conf import settings
from django.views.generic import RedirectView
from django.views.static import serve
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
    re_path(
        r"^media/(?P<path>.*)$",
        login_required(serve),
        kwargs={"document_root": settings.MEDIA_ROOT},
    ),
]
