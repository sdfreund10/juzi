from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.models import Learner
from api.serializers import LoginSerializer, StudyLevelSerializer

INVALID_CREDENTIALS = {"detail": "Invalid email or password."}


def _study_level_for(user) -> str | None:
    try:
        return user.learner.study_level
    except Learner.DoesNotExist:
        return None


def _user_payload(user) -> dict:
    return {
        "authenticated": True,
        # username and email are dual-written to the same login address.
        "email": user.email or user.get_username(),
        "study_level": _study_level_for(user),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def me(request: Request) -> Response:
    """Return the current session user, and ensure the CSRF cookie is set."""
    if request.user.is_authenticated:
        return Response(_user_payload(request.user))
    return Response({"authenticated": False, "email": None, "study_level": None})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    # ModelBackend runs a dummy password hasher when the email is unknown,
    # keeping response timing closer across valid/invalid accounts.
    user = authenticate(request, username=email, password=password)
    if user is None:
        return Response(INVALID_CREDENTIALS, status=status.HTTP_400_BAD_REQUEST)

    login(request, user)
    return Response(_user_payload(user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    logout(request)
    return Response({"authenticated": False, "email": None, "study_level": None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_study_level(request: Request) -> Response:
    serializer = StudyLevelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    level = serializer.validated_data["study_level"]

    learner, _ = Learner.objects.update_or_create(
        user=request.user,
        defaults={"study_level": level},
    )
    request.user.learner = learner
    return Response(_user_payload(request.user))
