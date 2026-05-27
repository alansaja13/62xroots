import hashlib
import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from growlog.models import APIToken


class Command(BaseCommand):
    help = 'Genera un API token seguro para un usuario existente'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'El usuario "{username}" no existe')

        raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        APIToken.objects.create(user=user, token_hash=token_hash)

        self.stdout.write(self.style.SUCCESS(f'Token creado para {username}:'))
        self.stdout.write(raw_token)
        self.stdout.write(self.style.WARNING(
            'ATENCION: Copia este token ahora, no puede recuperarse. Borralo de los logs de Railway.'
        ))
