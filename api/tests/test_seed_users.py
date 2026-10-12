import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_seed_users_creates_dev_accounts() -> None:
    call_command("seed_users")

    admin = User.objects.get(username="admin@test.com")
    assert admin.email == "admin@test.com"
    assert admin.check_password("learnchinese")
    assert admin.is_staff
    assert admin.is_superuser
    assert admin.is_active

    agent = User.objects.get(username="ux-agent@test.com")
    assert agent.email == "ux-agent@test.com"
    assert agent.check_password("testingbot")
    assert not agent.is_staff
    assert not agent.is_superuser
    assert agent.is_active


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_seed_users_is_idempotent_and_resets_password() -> None:
    call_command("seed_users")
    admin = User.objects.get(username="admin@test.com")
    admin.set_password("changed")
    admin.save()

    call_command("seed_users")

    admin.refresh_from_db()
    assert admin.check_password("learnchinese")
    assert User.objects.filter(email__in=["admin@test.com", "ux-agent@test.com"]).count() == 2


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_seed_users_refuses_when_not_debug() -> None:
    with pytest.raises(CommandError, match="DJANGO_DEBUG"):
        call_command("seed_users")

    assert User.objects.count() == 0
