from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from api.services.accounts import apply_login_email

# Dev-only accounts. Passwords are intentional fixtures for local sign-in.
DEV_USERS = (
    {
        "email": "admin@test.com",
        "password": "learnchinese",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "email": "ux-agent@test.com",
        "password": "testingbot",
        "is_staff": False,
        "is_superuser": False,
    },
)


def ensure_dev_user(
    *,
    email: str,
    password: str,
    is_staff: bool,
    is_superuser: bool,
) -> tuple[User, bool]:
    """Create or update a development user. Returns (user, created)."""
    try:
        user = User.objects.get(username=email)
        created = False
    except User.DoesNotExist:
        user = User()
        created = True

    apply_login_email(user, email)
    user.set_password(password)
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.is_active = True
    user.save()
    return user, created


class Command(BaseCommand):
    help = "Seed development login accounts (DEBUG only)"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_users only runs when DJANGO_DEBUG is true")

        for account in DEV_USERS:
            user, created = ensure_dev_user(**account)
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action} {user.email}")

        self.stdout.write(self.style.SUCCESS("Done."))
