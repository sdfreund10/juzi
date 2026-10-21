import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from api.models import Word

CHANGE_LIST = "/admin/api/word/"
FLAGGED_QUEUE = "/admin/api/word/?flag_status=flagged"


def _superuser() -> User:
    return User.objects.create_superuser(
        "admin@test.com",
        "admin@test.com",
        "local-test-password",
    )


def _staff_with_word_view() -> User:
    user = User.objects.create_user(
        "viewer@test.com",
        "viewer@test.com",
        "local-test-password",
        is_staff=True,
    )
    permission = Permission.objects.get(codename="view_word")
    user.user_permissions.add(permission)
    return user


def _staff_without_word_perms() -> User:
    return User.objects.create_user(
        "staff@test.com",
        "staff@test.com",
        "local-test-password",
        is_staff=True,
    )


def _seed_words() -> dict[str, Word]:
    reporter = User.objects.create_user(
        "reporter@test.com",
        "reporter@test.com",
        "local-test-password",
    )
    flagged = Word.objects.create(
        chinese="愛",
        simplified="爱",
        pinyin="ài",
        english_basic="to love",
        hsk_level=1,
        flagged_by=reporter,
    )
    unflagged = Word.objects.create(
        chinese="書",
        simplified="书",
        pinyin="shū",
        english_basic="book",
        hsk_level=1,
    )
    other_flagged = Word.objects.create(
        chinese="茶",
        simplified="茶",
        pinyin="chá",
        english_basic="tea",
        hsk_level=1,
        flagged_by=reporter,
    )
    return {
        "flagged": flagged,
        "unflagged": unflagged,
        "other_flagged": other_flagged,
        "reporter": reporter,
    }


@pytest.mark.django_db
def test_admin_user_add_page_renders() -> None:
    admin = _superuser()
    client = Client()
    client.force_login(admin)

    response = client.get("/admin/auth/user/add/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Password-based authentication" in body


@pytest.mark.django_db
def test_word_changelist_filters_by_flag_status() -> None:
    admin = _superuser()
    words = _seed_words()
    client = Client()
    client.force_login(admin)

    flagged = client.get(FLAGGED_QUEUE)
    unflagged = client.get(f"{CHANGE_LIST}?flag_status=unflagged")
    all_words = client.get(CHANGE_LIST)

    assert flagged.status_code == 200
    assert unflagged.status_code == 200
    assert all_words.status_code == 200

    flagged_body = flagged.content.decode()
    unflagged_body = unflagged.content.decode()
    all_body = all_words.content.decode()

    assert words["flagged"].chinese in flagged_body
    assert words["other_flagged"].chinese in flagged_body
    assert words["unflagged"].chinese not in flagged_body

    assert words["unflagged"].chinese in unflagged_body
    assert words["flagged"].chinese not in unflagged_body

    assert words["flagged"].chinese in all_body
    assert words["unflagged"].chinese in all_body


@pytest.mark.django_db
def test_word_changelist_combines_flag_status_with_search_and_reporter() -> None:
    admin = _superuser()
    words = _seed_words()
    client = Client()
    client.force_login(admin)
    reporter_id = words["reporter"].id

    response = client.get(
        f"{CHANGE_LIST}?flag_status=flagged"
        f"&flagged_by__id__exact={reporter_id}"
        f"&q=愛"
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert words["flagged"].chinese in body
    assert words["other_flagged"].chinese not in body
    assert words["unflagged"].chinese not in body


@pytest.mark.django_db
def test_word_changelist_shows_review_fields_and_edit_link() -> None:
    admin = _superuser()
    words = _seed_words()
    client = Client()
    client.force_login(admin)

    response = client.get(FLAGGED_QUEUE)

    assert response.status_code == 200
    body = response.content.decode()
    word = words["flagged"]
    change_url = reverse("admin:api_word_change", args=[word.pk])

    assert word.chinese in body
    assert word.pinyin in body
    assert word.english_basic in body
    assert str(word.hsk_level) in body
    assert words["reporter"].username in body
    assert f'href="{change_url}' in body
    assert f'>{word.chinese}</a>' in body


@pytest.mark.django_db
def test_admin_index_shows_flagged_queue_link_for_word_viewers() -> None:
    viewer = _staff_with_word_view()
    client = Client()
    client.force_login(viewer)

    response = client.get("/admin/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Flagged words" in body
    assert FLAGGED_QUEUE in body or "/admin/api/word/?flag_status=flagged" in body


@pytest.mark.django_db
def test_admin_index_hides_flagged_queue_link_without_word_permission() -> None:
    staff = _staff_without_word_perms()
    client = Client()
    client.force_login(staff)

    response = client.get("/admin/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Flagged words" not in body
    assert "flag_status=flagged" not in body


@pytest.mark.django_db
def test_word_queue_allows_staff_with_view_permission() -> None:
    viewer = _staff_with_word_view()
    words = _seed_words()
    client = Client()
    client.force_login(viewer)

    queue = client.get(FLAGGED_QUEUE)
    change = client.get(reverse("admin:api_word_change", args=[words["flagged"].pk]))

    assert queue.status_code == 200
    assert change.status_code == 200


@pytest.mark.django_db
def test_word_queue_forbids_staff_without_word_permission() -> None:
    staff = _staff_without_word_perms()
    words = _seed_words()
    client = Client()
    client.force_login(staff)

    queue = client.get(FLAGGED_QUEUE)
    change = client.get(reverse("admin:api_word_change", args=[words["flagged"].pk]))

    assert queue.status_code == 403
    assert change.status_code == 403


@pytest.mark.django_db
def test_word_queue_redirects_anonymous_and_non_staff() -> None:
    words = _seed_words()
    learner = User.objects.create_user(
        "learner@test.com",
        "learner@test.com",
        "local-test-password",
    )
    client = Client()

    anonymous_queue = client.get(FLAGGED_QUEUE)
    anonymous_change = client.get(
        reverse("admin:api_word_change", args=[words["flagged"].pk])
    )

    client.force_login(learner)
    learner_queue = client.get(FLAGGED_QUEUE)
    learner_change = client.get(
        reverse("admin:api_word_change", args=[words["flagged"].pk])
    )

    assert anonymous_queue.status_code == 302
    assert "/admin/login/" in anonymous_queue["Location"]
    assert anonymous_change.status_code == 302
    assert "/admin/login/" in anonymous_change["Location"]
    assert learner_queue.status_code == 302
    assert "/admin/login/" in learner_queue["Location"]
    assert learner_change.status_code == 302
    assert "/admin/login/" in learner_change["Location"]
