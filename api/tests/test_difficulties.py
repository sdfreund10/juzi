from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from api.models import Learner, UserWord, Word
from api.services.accounts import apply_login_email
from api.services.difficulties import easy_count_floor

User = get_user_model()

MODE_1 = (UserWord.Mode.PINYIN_TO_EN,)
MODE_2 = (UserWord.Mode.PINYIN_TO_EN, UserWord.Mode.EN_TO_ZH)
MODE_3 = (
    UserWord.Mode.PINYIN_TO_EN,
    UserWord.Mode.EN_TO_ZH,
    UserWord.Mode.ZH_TO_EN,
)


@pytest.fixture
def user(db) -> User:
    user = User(username="alice@example.com", email="alice@example.com")
    apply_login_email(user, "alice@example.com")
    user.set_password("s3cret")
    user.save()
    return user


@pytest.fixture
def words(db) -> dict[str, Word]:
    return {
        "beginner": Word.objects.create(
            chinese="愛",
            simplified="爱",
            pinyin="ài",
            english_basic="to love",
            hsk_level=1,
        ),
        "intermediate": Word.objects.create(
            chinese="圖書館",
            simplified="图书馆",
            pinyin="túshūguǎn",
            english_basic="library",
            hsk_level=4,
        ),
        "advanced": Word.objects.create(
            chinese="抽象",
            simplified="抽象",
            pinyin="chōuxiàng",
            english_basic="abstract",
            hsk_level=6,
        ),
    }


@pytest.mark.parametrize(
    ("easy_count", "expected"),
    [
        (0, MODE_1),
        (4, MODE_1),
        (5, MODE_2),
        (9, MODE_2),
        (10, MODE_3),
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
def test_unlocked_modes_for_row_includes_hsk_3_in_early_band(user: User) -> None:
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
def test_unlocked_modes_for_row_uses_easy_count_above_floor(
    user: User,
    words: dict[str, Word],
) -> None:
    Learner.objects.create(user=user, study_level=Learner.StudyLevel.INTERMEDIATE)
    row = UserWord.objects.create(
        user=user,
        word=words["advanced"],
        easy_count=10,
        due_on=timezone.localdate(),
    )
    row = UserWord.objects.select_related("word", "user__learner").get(pk=row.pk)
    assert unlocked_modes_for_row(row) == MODE_3
