from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Create or update the demo users used for testing.'

    users = (
        {
            'username': 'demo_user',
            'email': 'demo_user@example.com',
            'password': 'NeuralDemo2026!',
            'is_staff': False,
            'is_superuser': False,
        },
        {
            'username': 'demo_admin',
            'email': 'demo_admin@example.com',
            'password': 'NeuralAdmin2026!',
            'is_staff': True,
            'is_superuser': True,
        },
    )

    def handle(self, *args, **options):
        for user_definition in self.users:
            user_data = user_definition.copy()
            password = user_data.pop('password')
            username = user_data.pop('username')
            user, created = User.objects.get_or_create(
                username=username,
                defaults=user_data,
            )
            user.email = user_data['email']
            user.is_staff = user_data['is_staff']
            user.is_superuser = user_data['is_superuser']
            user.set_password(password)
            user.save()
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{action} {username}'))
