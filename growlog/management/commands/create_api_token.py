from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from growlog.models import APIToken


class Command(BaseCommand):
    help = 'Genera un API token para un usuario existente'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'El usuario "{username}" no existe')

        token = APIToken.objects.create(user=user)
        self.stdout.write(self.style.SUCCESS(f'Token creado para {username}:'))
        self.stdout.write(str(token.token))
