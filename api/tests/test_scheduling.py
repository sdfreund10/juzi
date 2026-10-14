from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Category, Learner, UserWord, Word, WordCategory
from api.services.accounts import apply_login_email
from api.services.scheduling import (
    GRADE_EASY,
    GRADE_HARD,
    UserWordNotFoundError,
    easy_count_floor,
    interval_days_for_streak,
    rate_user_word,
    unlocked_modes_for_count,
    unlocked_modes_for_row,
)
from api.services.sessions import EmptySessionError, build_session

User = get_user_model()


def _make_user(*, email: str, password: str = "s3cret") -> User:
    user = User(username=email, email=email)
    apply_login_email(user, email)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def user(db) -> User:
    return _make_user(email="alice@example.com")


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def _csrf_headers(client: APIClient) -> dict[str, str]:
    response = client.get(reverse("auth-me"))
    assert response.status_code == status.HTTP_200_OK
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def _login(client: APIClient, user: User, password: str = "s3cret") -> dict[str, str]:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": password},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_200_OK
    return _csrf_headers(client)


@pytest.fixture
def topic(db) -> Category:
    return Category.objects.create(name="Food, Cooking & Dining")


@pytest.fixture
def words(topic: Category) -> dict[str, Word]:
    beginner = Word.objects.create(
        chinese="愛",
        simplified="爱",
        pinyin="ài",
        english_basic="to love",
        hsk_level=1,
    )
    intermediate = Word.objects.create(
        chinese="圖書館",
        simplified="图书馆",
        pinyin="túshūguǎn",
        english_basic="library",
        hsk_level=4,
    )
    advanced = Word.objects.create(
        chinese="抽象",
        simplified="抽象",
        pinyin="chōuxiàng",
        english_basic="abstract",
        hsk_level=6,
    )
    for word in (beginner, intermediate, advanced):
        WordCategory.objects.create(word=word, category=topic)
    return {
        "beginner": beginner,
        "intermediate": intermediate,
        "advanced": advanced,
    }


@pytest.mark.parametrize(
    ("streak", "expected_days"),
    [
        (1, 1),
        (3, 3),
        (4, 3),
        (6, 7),
        (9, 7),
        (10, 14),
        (20, 14),
    ],
)
def test_interval_days_for_streak(streak: int, expected_days: int) -> None:
    assert interval_days_for_streak(streak) == expected_days


@pytest.mark.parametrize(
    ("easy_count", "expected"),
    [
        (0, (UserWord.Mode.PINYIN_TO_EN,)),
        (4, (UserWord.Mode.PINYIN_TO_EN,)),
        (
            5,
            (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH),
        ),
        (
            9,
            (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH),
        ),
        (
            10,
            (
                UserWord.Mode.PINYIN_TO_EN,
                UserWord.Mode.EN_TO_ZH,
                UserWord.Mode.ZH_TO_EN,
            ),
        ),
    ],
)
def test_unlocked_modes_for_count(easy_count: int, expected: tuple[str, ...]) -> None:
    assert unlocked_modes_for_count(easy_count) == expected


@pytest.mark.parametrize(
    ("study_level", "hsk_level", "expected_floor"),
    [
        (None, 1, 0),
        (Learner.StudyLevel.NOVICE, 1, 0),
        (Learner.StudyLevel.NOVICE, 6, 0),
        (Learner.StudyLevel.INTERMEDIATE, 1, 5),
        (Learner.StudyLevel.INTERMEDIATE, 3, 5),
        (Learner.StudyLevel.INTERMEDIATE, 4, 0),
        (Learner.StudyLevel.ADVANCED, 1, 10),
        (Learner.StudyLevel.ADVANCED, 3, 10),
        (Learner.StudyLevel.ADVANCED, 4, 5),
        (Learner.StudyLevel.SUPERIOR, 1, 10),
        (Learner.StudyLevel.SUPERIOR, 6, 10),
    ],
)
def test_easy_count_floor(
    study_level: str | None,
    hsk_level: int,
    expected_floor: int,
) -> None:
    assert easy_count_floor(study_level, hsk_level) == expected_floor


MODE_1 = (UserWord.Mode.PINYIN_TO_EN,)
MODE_2 = (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH)
MODE_3 = (
    UserWord.Mode.PINYIN_TO_EN,
    UserWord.Mode.EN_TO_ZH,
    UserWord.Mode.ZH_TO_EN,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("study_level", "word_key", "expected"),
    [
        (Learner.StudyLevel.NOVICE, "beginner", MODE_1),
        (Learner.StudyLevel.NOVICE, "intermediate", MODE_1),
        (Learner.StudyLevel.INTERMEDIATE, "beginner", MODE_2),
        (Learner.StudyLevel.INTERMEDIATE, "intermediate", MODE_1),
        (Learner.StudyLevel.ADVANCED, "beginner", MODE_3),
        (Learner.StudyLevel.ADVANCED, "intermediate", MODE_2),
        (Learner.StudyLevel.SUPERIOR, "beginner", MODE_3),
        (Learner.StudyLevel.SUPERIOR, "advanced", MODE_3),
    ],
)
def test_unlocked_modes_for_row_uses_study_level_floor(
    user: User,
    words: dict[str, Word],
    study_level: str,
    word_key: str,
    expected: tuple[str, ...],
) -> None:
    Learner.objects.create(user=user, study_level=study_level)
    row = UserWord.objects.create(
        user=user,
        word=words[word_key],
        easy_count=0,
        due_on=timezone.localdate(),
    )
    row = UserWord.objects.select_related("word", "user__learner").get(pk=row.pk)
    assert unlocked_modes_for_row(row) == expected


@pytest.mark.django_db
def test_unlocked_modes_for_row_includes_hsk_3_in_early_band(
    user: User,
) -> None:
    Learner.objects.create(user=user, study_level=Learner.StudyLevel.INTERMEDIATE)
    word = Word.objects.create(
        chinese="麵",
        simplified="面",
        pinyin="miàn",
        english_basic="noodles",
        hsk_level=3,
    )
    row = UserWord.objects.create(
        user=user,
        word=word,
        easy_count=0,
        due_on=timezone.localdate(),
    )
    row = UserWord.objects.select_related("word", "user__learner").get(pk=row.pk)
    assert unlocked_modes_for_row(row) == MODE_2


@pytest.mark.django_db
def test_rate_easy_does_not_announce_floor_modes(
    user: User,
    words: dict[str, Word],
) -> None:
    Learner.objects.create(user=user, study_level=Learner.StudyLevel.INTERMEDIATE)
    row = UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_streak=4,
        easy_count=4,
        due_on=timezone.localdate(),
    )

    result = rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_EASY,
    )

    assert result.unlocked_modes == MODE_2
    assert result.newly_unlocked_modes == ()


@pytest.mark.django_db
def test_rate_easy_can_unlock_beyond_floor(
    user: User,
    words: dict[str, Word],
) -> None:
    Learner.objects.create(user=user, study_level=Learner.StudyLevel.INTERMEDIATE)
    row = UserWord.objects.create(
        user=user,
        word=words["advanced"],
        easy_streak=9,
        easy_count=9,
        due_on=timezone.localdate(),
    )

    result = rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_EASY,
    )

    assert result.unlocked_modes == MODE_3
    assert result.newly_unlocked_modes == (UserWord.Mode.ZH_TO_EN,)


@pytest.mark.django_db
def test_rate_hard_resets_streak_keeps_count(user: User, words: dict[str, Word]) -> None:
    today = timezone.localdate()
    row = UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_streak=4,
        easy_count=7,
        due_on=today + timedelta(days=3),
    )

    result = rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_HARD,
    )

    row.refresh_from_db()
    assert row.easy_streak == 0
    assert row.easy_count == 7
    assert row.due_on == today
    assert row.last_practiced_at is not None
    assert result.newly_unlocked_modes == ()


@pytest.mark.django_db
def test_rate_easy_advances_streak_count_and_due(user: User, words: dict[str, Word]) -> None:
    today = timezone.localdate()
    row = UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_streak=0,
        easy_count=0,
        due_on=today,
    )

    result = rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_EASY,
    )

    row.refresh_from_db()
    assert row.easy_streak == 1
    assert row.easy_count == 1
    assert row.due_on == today + timedelta(days=1)
    assert row.last_practiced_at is not None
    assert result.unlocked_modes == (UserWord.Mode.PINYIN_TO_EN,)


@pytest.mark.django_db
def test_rate_easy_unlocks_en_to_zh_at_threshold(user: User, words: dict[str, Word]) -> None:
    today = timezone.localdate()
    row = UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_streak=4,
        easy_count=4,
        due_on=today,
    )

    result = rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_EASY,
    )

    row.refresh_from_db()
    assert row.easy_count == 5
    assert result.unlocked_modes == (
        UserWord.Mode.PINYIN_TO_EN,
        UserWord.Mode.EN_TO_ZH,
    )
    assert result.newly_unlocked_modes == (UserWord.Mode.EN_TO_ZH,)


@pytest.mark.django_db
def test_rate_easy_unlocks_zh_to_en_at_double_threshold(
    user: User,
    words: dict[str, Word],
) -> None:
    today = timezone.localdate()
    row = UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_streak=9,
        easy_count=9,
        due_on=today,
    )

    result = rate_user_word(
        user=user,
        word_id=row.word_id,
        grade=GRADE_EASY,
    )

    row.refresh_from_db()
    assert row.easy_count == 10
    assert result.unlocked_modes == (
        UserWord.Mode.PINYIN_TO_EN,
        UserWord.Mode.EN_TO_ZH,
        UserWord.Mode.ZH_TO_EN,
    )
    assert result.newly_unlocked_modes == (UserWord.Mode.ZH_TO_EN,)


@pytest.mark.django_db
def test_rate_missing_user_word_raises(user: User, words: dict[str, Word]) -> None:
    with pytest.raises(UserWordNotFoundError):
        rate_user_word(
            user=user,
            word_id=words["beginner"].id,
            grade=GRADE_EASY,
        )


@pytest.mark.django_db
def test_build_session_lazily_creates_difficulty_scoped_rows(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    session = build_session(
        user=user,
        category=topic,
        difficulties=["beginner"],
    )

    assert session.total == 1
    assert session.cards[0].word_id == words["beginner"].id
    assert UserWord.objects.filter(user=user).count() == 1
    row = UserWord.objects.get(user=user, word=words["beginner"])
    assert row.due_on == timezone.localdate()
    assert not UserWord.objects.filter(user=user, word=words["intermediate"]).exists()
    assert not UserWord.objects.filter(user=user, word=words["advanced"]).exists()


@pytest.mark.django_db
def test_build_session_one_card_per_word_and_unlocked_mode(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_count=10,
        due_on=timezone.localdate(),
    )

    with patch("api.services.sessions.random.choice", return_value=UserWord.Mode.ZH_TO_EN):
        session = build_session(
            user=user,
            category=topic,
            difficulties=["beginner"],
        )

    assert session.total == 1
    card = session.cards[0]
    assert card.word_id == words["beginner"].id
    assert card.mode == UserWord.Mode.ZH_TO_EN
    assert card.prompt == words["beginner"].chinese


@pytest.mark.django_db
def test_build_session_superior_can_serve_zh_to_en(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    Learner.objects.create(user=user, study_level=Learner.StudyLevel.SUPERIOR)
    UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_count=0,
        due_on=timezone.localdate(),
    )

    with patch("api.services.sessions.random.choice", return_value=UserWord.Mode.ZH_TO_EN):
        session = build_session(
            user=user,
            category=topic,
            difficulties=["beginner"],
        )

    assert session.cards[0].mode == UserWord.Mode.ZH_TO_EN


@pytest.mark.django_db
def test_build_session_intermediate_cannot_serve_zh_to_en_on_hsk_6(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    Learner.objects.create(user=user, study_level=Learner.StudyLevel.INTERMEDIATE)
    UserWord.objects.create(
        user=user,
        word=words["advanced"],
        easy_count=0,
        due_on=timezone.localdate(),
    )

    with patch(
        "api.services.sessions.random.choice",
        side_effect=lambda modes: (
            UserWord.Mode.ZH_TO_EN
            if UserWord.Mode.ZH_TO_EN in modes
            else modes[0]
        ),
    ):
        session = build_session(
            user=user,
            category=topic,
            difficulties=["advanced"],
        )

    assert session.cards[0].mode == UserWord.Mode.PINYIN_TO_EN


@pytest.mark.django_db
def test_build_session_excludes_future_due(
    user: User,
    topic: Category,
    words: dict[str, Word],
) -> None:
    UserWord.objects.create(
        user=user,
        word=words["beginner"],
        due_on=timezone.localdate() + timedelta(days=1),
    )

    with pytest.raises(EmptySessionError):
        build_session(
            user=user,
            category=topic,
            difficulties=["beginner"],
        )


@pytest.mark.django_db
def test_rate_endpoint_requires_authentication(
    client: APIClient,
    words: dict[str, Word],
) -> None:
    headers = _csrf_headers(client)
    response = client.post(
        reverse("ratings-create"),
        {"word_id": words["beginner"].id, "grade": "easy"},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_rate_endpoint_happy_path(
    client: APIClient,
    user: User,
    words: dict[str, Word],
) -> None:
    today = timezone.localdate()
    UserWord.objects.create(
        user=user,
        word=words["beginner"],
        easy_streak=0,
        easy_count=0,
        due_on=today,
    )
    headers = _login(client, user)
    response = client.post(
        reverse("ratings-create"),
        {"word_id": words["beginner"].id, "grade": "easy"},
        format="json",
        **headers,
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["user_word"]["word_id"] == words["beginner"].id
    assert body["user_word"]["easy_streak"] == 1
    assert body["user_word"]["easy_count"] == 1
    assert body["unlocked_modes"] == [UserWord.Mode.PINYIN_TO_EN]
    assert body["newly_unlocked_modes"] == []


@pytest.mark.django_db
def test_rate_endpoint_missing_row(
    client: APIClient,
    user: User,
    words: dict[str, Word],
) -> None:
    headers = _login(client, user)
    response = client.post(
        reverse("ratings-create"),
        {"word_id": words["beginner"].id, "grade": "hard"},
        format="json",
        **headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Word progress not found."}
