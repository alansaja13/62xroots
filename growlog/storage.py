from django.urls import reverse
from storages.backends.s3 import S3Storage


class PrivateMediaStorage(S3Storage):
    """El navegador descarga fotos a través de la autorización de Django."""

    def url(self, name, parameters=None, expire=None, http_method=None):
        return reverse("protected_media", kwargs={"path": name})
