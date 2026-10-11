import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory

from api.services.accounts import apply_login_email, normalize_login_email

User = get_user_model()


def _make_user(*, email: str, password: str) -> User:
    user = User(username=email, email=email)
    apply_login_email(user, email)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def user(db) -> User:
    return _make_user(email="alice@example.com", password="s3cret-alice")


@pytest.fixture
def other_user(db) -> User:
    return _make_user(email="bob@example.com", password="s3cret-bob")


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    token = client.cookies["csrftoken"].value
    return {"HTTP_X_CSRFTOKEN": token}


@pytest.mark.django_db
def test_me_anonymous_sets_csrf_cookie(client: APIClient) -> None:
    response = client.get(reverse("auth-me"))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"authenticated": False, "email": None}
    assert "csrftoken" in client.cookies


@pytest.mark.django_db
def test_login_rejects_bad_credentials_without_field_hints(client: APIClient, user: User) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": "alice@example.com", "password": "wrong"},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body == {"detail": "Invalid email or password."}
    assert "email" not in body
    assert "password" not in body


@pytest.mark.django_db
def test_login_is_case_insensitive_for_email(client: APIClient, user: User) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": "Alice@Example.com", "password": "s3cret-alice"},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"authenticated": True, "email": "alice@example.com"}


@pytest.mark.django_db
def test_apply_login_email_dual_writes_and_lowercases(db) -> None:
    user = User()
    assert apply_login_email(user, "Carol@Example.com") == "carol@example.com"
    assert user.username == "carol@example.com"
    assert user.email == "carol@example.com"


def test_apply_login_email_rejects_non_email() -> None:
    with pytest.raises(ValidationError):
        apply_login_email(User(), "not-an-email")


def test_normalize_login_email() -> None:
    assert normalize_login_email("  A@B.com ") == "a@b.com"


@pytest.mark.django_db
def test_login_validation_errors_use_field_keys(client: APIClient) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": "not-an-email", "password": "whatever"},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert "email" in body
    assert "detail" not in body


@pytest.mark.django_db
def test_login_logout_and_me_roundtrip(client: APIClient, user: User) -> None:
    headers = _csrf_headers(client)

    login_response = client.post(
        reverse("auth-login"),
        {"email": "alice@example.com", "password": "s3cret-alice"},
        format="json",
        **headers,
    )
    assert login_response.status_code == status.HTTP_200_OK
    assert login_response.json() == {"authenticated": True, "email": "alice@example.com"}

    me_response = client.get(reverse("auth-me"))
    assert me_response.status_code == status.HTTP_200_OK
    assert me_response.json() == {"authenticated": True, "email": "alice@example.com"}

    # Session auth re-enforces CSRF once logged in.
    headers = _csrf_headers(client)
    logout_response = client.post(reverse("auth-logout"), format="json", **headers)
    assert logout_response.status_code == status.HTTP_200_OK
    assert logout_response.json() == {"authenticated": False, "email": None}

    me_after = client.get(reverse("auth-me"))
    assert me_after.json() == {"authenticated": False, "email": None}


@pytest.mark.django_db
def test_logout_requires_authentication(client: APIClient) -> None:
    headers = _csrf_headers(client)
    response = client.post(reverse("auth-logout"), format="json", **headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_default_permission_rejects_anonymous() -> None:
    """Future study endpoints inherit IsAuthenticated and must reject anonymous callers."""

    @api_view(["GET"])
    def probe(request):
        return Response({"ok": True})

    factory = APIRequestFactory()
    request = factory.get("/probe/")
    response = probe(request)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_userword_fk_isolates_rows_per_user(user: User, other_user: User) -> None:
    """Model-level FK isolation only; API queryset scoping lands with deck endpoints."""
    from api.models import UserWord, Word

    word = Word.objects.create(
        chinese="字",
        simplified="字",
        pinyin="zì",
        english_basic="character",
    )
    UserWord.objects.create(user=user, word=word)
    UserWord.objects.create(user=other_user, word=word)

    assert UserWord.objects.filter(user=user).count() == 1
    assert UserWord.objects.filter(user=other_user).count() == 1
    assert UserWord.objects.filter(user=user).get().user_id == user.id
