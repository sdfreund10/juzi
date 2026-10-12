from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.models import Category, UserWord
from api.serializers import CreateSessionSerializer, RateCardSerializer
from api.services.categories import list_topic_categories
from api.services.scheduling import UserWordNotFoundError, rate_user_word
from api.services.sessions import EmptySessionError, StudySession, build_session


def _category_list_payload(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "beginner_count": category.beginner_count,
        "intermediate_count": category.intermediate_count,
        "advanced_count": category.advanced_count,
        "last_practiced_at": (
            category.last_practiced_at.isoformat() if category.last_practiced_at else None
        ),
    }


def _session_payload(session: StudySession) -> dict:
    return {
        "category": {
            "id": session.category.id,
            "name": session.category.name,
        },
        "difficulties": session.difficulties,
        "total": session.total,
        "cards": [
            {
                "word_id": card.word_id,
                "mode": card.mode,
                "prompt": card.prompt,
                "answer_chinese": card.answer_chinese,
                "answer_pinyin": card.answer_pinyin,
                "answer_english": card.answer_english,
                "example_chinese": card.example_chinese,
                "example_pinyin": card.example_pinyin,
                "example_english": card.example_english,
            }
            for card in session.cards
        ],
    }


def _user_word_payload(
    user_word: UserWord, *, unlocked_modes: tuple[str, ...], newly_unlocked_modes: tuple[str, ...]
) -> dict:
    return {
        "user_word": {
            "id": user_word.id,
            "word_id": user_word.word_id,
            "easy_streak": user_word.easy_streak,
            "easy_count": user_word.easy_count,
            "due_on": user_word.due_on.isoformat() if user_word.due_on else None,
            "last_practiced_at": (
                user_word.last_practiced_at.isoformat() if user_word.last_practiced_at else None
            ),
        },
        "unlocked_modes": list(unlocked_modes),
        "newly_unlocked_modes": list(newly_unlocked_modes),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def categories(request: Request) -> Response:
    return Response(
        [_category_list_payload(category) for category in list_topic_categories(user=request.user)]
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_session(request: Request) -> Response:
    serializer = CreateSessionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    category_id = serializer.validated_data["category_id"]
    difficulties = serializer.validated_data["difficulties"]

    try:
        category = Category.objects.get(pk=category_id)
    except Category.DoesNotExist:
        return Response(
            {"detail": "Category not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        session = build_session(
            user=request.user,
            category=category,
            difficulties=difficulties,
        )
    except EmptySessionError:
        return Response(
            {"detail": "No cards match."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(_session_payload(session), status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rate_card(request: Request) -> Response:
    # TODO: add custom Sentry tracing once available; this path must stay fast.
    serializer = RateCardSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        result = rate_user_word(
            user=request.user,
            word_id=serializer.validated_data["word_id"],
            grade=serializer.validated_data["grade"],
        )
    except UserWordNotFoundError:
        return Response(
            {"detail": "Word progress not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        _user_word_payload(
            result.user_word,
            unlocked_modes=result.unlocked_modes,
            newly_unlocked_modes=result.newly_unlocked_modes,
        ),
        status=status.HTTP_200_OK,
    )
