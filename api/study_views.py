from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.models import Category
from api.serializers import CreateSessionSerializer
from api.services.categories import list_topic_categories
from api.services.sessions import EmptySessionError, StudySession, build_session


def _category_list_payload(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "beginner_count": category.beginner_count,
        "intermediate_count": category.intermediate_count,
        "advanced_count": category.advanced_count,
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
            }
            for card in session.cards
        ],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def categories(request: Request) -> Response:
    return Response(
        [_category_list_payload(category) for category in list_topic_categories()]
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
