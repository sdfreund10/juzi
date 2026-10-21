import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from api.models import Category, UserWord, Word, WordCategory

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


def _staff_with_word_change() -> User:
    user = User.objects.create_user(
        "editor@test.com",
        "editor@test.com",
        "local-test-password",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="view_word"),
        Permission.objects.get(codename="change_word"),
    )
    return user


def _staff_without_word_perms() -> User:
    return User.objects.create_user(
        "staff@test.com",
        "staff@test.com",
        "local-test-password",
        is_staff=True,
    )


def _word_form_data(word: Word, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "chinese": word.chinese,
        "simplified": word.simplified,
        "pinyin": word.pinyin,
        "english_basic": word.english_basic,
        "hsk_level": word.hsk_level,
        "example_sentence_traditional": word.example_sentence_traditional,
        "example_sentence_simplified": word.example_sentence_simplified,
        "example_sentence_pinyin": word.example_sentence_pinyin,
        "example_sentence_english": word.example_sentence_english,
    }
    data.update(overrides)
    return data


def _change_logs_for(word: Word) -> list[LogEntry]:
    content_type = ContentType.objects.get_for_model(Word)
    return list(
        LogEntry.objects.filter(
            content_type=content_type,
            object_id=str(word.pk),
            action_flag=CHANGE,
        )
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
        f"{CHANGE_LIST}?flag_status=flagged&flagged_by__id__exact={reporter_id}&q=愛"
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
    assert f">{word.chinese}</a>" in body


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
    anonymous_change = client.get(reverse("admin:api_word_change", args=[words["flagged"].pk]))

    client.force_login(learner)
    learner_queue = client.get(FLAGGED_QUEUE)
    learner_change = client.get(reverse("admin:api_word_change", args=[words["flagged"].pk]))

    assert anonymous_queue.status_code == 302
    assert "/admin/login/" in anonymous_queue["Location"]
    assert anonymous_change.status_code == 302
    assert "/admin/login/" in anonymous_change["Location"]
    assert learner_queue.status_code == 302
    assert "/admin/login/" in learner_queue["Location"]
    assert learner_change.status_code == 302
    assert "/admin/login/" in learner_change["Location"]


@pytest.mark.django_db
def test_word_change_form_sections_and_save_and_unflag_button() -> None:
    admin = _superuser()
    words = _seed_words()
    client = Client()
    client.force_login(admin)

    flagged = client.get(reverse("admin:api_word_change", args=[words["flagged"].pk]))
    unflagged = client.get(reverse("admin:api_word_change", args=[words["unflagged"].pk]))

    assert flagged.status_code == 200
    flagged_body = flagged.content.decode()
    assert "Vocabulary" in flagged_body
    assert "Example" in flagged_body
    assert "Review" in flagged_body
    assert "Reporter" in flagged_body
    assert words["reporter"].username in flagged_body
    assert 'name="_save"' in flagged_body
    assert 'name="_save_and_unflag"' in flagged_body
    assert 'name="flagged_by"' not in flagged_body

    assert unflagged.status_code == 200
    unflagged_body = unflagged.content.decode()
    assert 'name="_save"' in unflagged_body
    assert 'name="_save_and_unflag"' not in unflagged_body


@pytest.mark.django_db
def test_ordinary_save_keeps_flag_and_updates_content() -> None:
    admin = _superuser()
    words = _seed_words()
    word = words["flagged"]
    client = Client()
    client.force_login(admin)

    response = client.post(
        reverse("admin:api_word_change", args=[word.pk]),
        {
            **_word_form_data(word, english_basic="to love deeply"),
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    word.refresh_from_db()
    assert word.english_basic == "to love deeply"
    assert word.flagged_by_id == words["reporter"].id


@pytest.mark.django_db
def test_save_and_unflag_clears_flag_atomically_with_content() -> None:
    admin = _superuser()
    words = _seed_words()
    word = words["flagged"]
    client = Client()
    client.force_login(admin)

    response = client.post(
        reverse("admin:api_word_change", args=[word.pk]),
        {
            **_word_form_data(word, english_basic="affection"),
            "_save_and_unflag": "Save and unflag",
        },
    )

    assert response.status_code == 302
    word.refresh_from_db()
    assert word.english_basic == "affection"
    assert word.flagged_by_id is None
    logs = _change_logs_for(word)
    assert logs
    assert any("flagged_by" in entry.change_message for entry in logs)


@pytest.mark.django_db
def test_invalid_save_and_unflag_leaves_content_and_flag_unchanged() -> None:
    admin = _superuser()
    words = _seed_words()
    word = words["flagged"]
    original_english = word.english_basic
    client = Client()
    client.force_login(admin)

    response = client.post(
        reverse("admin:api_word_change", args=[word.pk]),
        {
            **_word_form_data(word, english_basic="x" * 300),
            "_save_and_unflag": "Save and unflag",
        },
    )

    assert response.status_code == 200
    word.refresh_from_db()
    assert word.english_basic == original_english
    assert word.flagged_by_id == words["reporter"].id
    assert not _change_logs_for(word)


@pytest.mark.django_db
def test_save_and_unflag_preserves_identity_progress_and_decks() -> None:
    admin = _superuser()
    words = _seed_words()
    word = words["flagged"]
    learner = User.objects.create_user(
        "alice@test.com",
        "alice@test.com",
        "local-test-password",
    )
    category = Category.objects.create(name="Food")
    membership = WordCategory.objects.create(word=word, category=category)
    progress = UserWord.objects.create(
        user=learner,
        word=word,
        easy_streak=2,
        easy_count=3,
    )
    word_id = word.pk
    client = Client()
    client.force_login(admin)

    response = client.post(
        reverse("admin:api_word_change", args=[word.pk]),
        {
            **_word_form_data(word, pinyin="ài"),
            "_save_and_unflag": "Save and unflag",
        },
    )

    assert response.status_code == 302
    word.refresh_from_db()
    progress.refresh_from_db()
    membership.refresh_from_db()
    assert word.pk == word_id
    assert word.flagged_by_id is None
    assert progress.word_id == word_id
    assert progress.easy_streak == 2
    assert progress.easy_count == 3
    assert membership.word_id == word_id
    assert membership.category_id == category.pk


@pytest.mark.django_db
def test_save_and_unflag_requires_change_permission() -> None:
    viewer = _staff_with_word_view()
    editor = _staff_with_word_change()
    words = _seed_words()
    word = words["flagged"]
    change_url = reverse("admin:api_word_change", args=[word.pk])

    viewer_client = Client()
    viewer_client.force_login(viewer)
    viewer_get = viewer_client.get(change_url)
    viewer_post = viewer_client.post(
        change_url,
        {
            **_word_form_data(word, english_basic="blocked"),
            "_save_and_unflag": "Save and unflag",
        },
    )

    assert viewer_get.status_code == 200
    assert 'name="_save_and_unflag"' not in viewer_get.content.decode()
    assert viewer_post.status_code == 403
    word.refresh_from_db()
    assert word.english_basic == "to love"
    assert word.flagged_by_id == words["reporter"].id

    editor_client = Client()
    editor_client.force_login(editor)
    editor_post = editor_client.post(
        change_url,
        {
            **_word_form_data(word, english_basic="allowed"),
            "_save_and_unflag": "Save and unflag",
        },
    )

    assert editor_post.status_code == 302
    word.refresh_from_db()
    assert word.english_basic == "allowed"
    assert word.flagged_by_id is None


@pytest.mark.django_db
def test_word_changelist_defaults_to_active_and_filters_archive_status() -> None:
    admin = _superuser()
    words = _seed_words()
    words["flagged"].archived_at = timezone.now()
    words["flagged"].save(update_fields=["archived_at"])
    client = Client()
    client.force_login(admin)

    default_list = client.get(CHANGE_LIST)
    archived = client.get(f"{CHANGE_LIST}?archive_status=archived")
    all_words = client.get(f"{CHANGE_LIST}?archive_status=all")
    flagged_queue = client.get(FLAGGED_QUEUE)

    assert default_list.status_code == 200
    default_body = default_list.content.decode()
    assert words["unflagged"].chinese in default_body
    assert words["flagged"].chinese not in default_body

    archived_body = archived.content.decode()
    assert words["flagged"].chinese in archived_body
    assert words["unflagged"].chinese not in archived_body

    all_body = all_words.content.decode()
    assert words["flagged"].chinese in all_body
    assert words["unflagged"].chinese in all_body

    # Default review queue stays on active flagged words.
    flagged_body = flagged_queue.content.decode()
    assert words["other_flagged"].chinese in flagged_body
    assert words["flagged"].chinese not in flagged_body


@pytest.mark.django_db
def test_word_admin_disables_hard_delete() -> None:
    admin = _superuser()
    words = _seed_words()
    client = Client()
    client.force_login(admin)

    change = client.get(reverse("admin:api_word_change", args=[words["flagged"].pk]))
    delete = client.get(
        reverse("admin:api_word_delete", args=[words["flagged"].pk]),
        follow=False,
    )
    bulk = client.post(
        CHANGE_LIST,
        {
            "action": "delete_selected",
            "_selected_action": [words["flagged"].pk],
        },
        follow=False,
    )
    body = change.content.decode()

    assert change.status_code == 200
    assert "Archive" in body
    assert 'value="Delete"' not in body
    assert ">Delete<" not in body
    assert delete.status_code in {403, 302}
    assert bulk.status_code in {200, 302}
    assert Word.objects.filter(pk=words["flagged"].pk).exists()


@pytest.mark.django_db
def test_archive_and_restore_word_preserves_flag_progress_and_decks() -> None:
    admin = _superuser()
    words = _seed_words()
    word = words["flagged"]
    learner = User.objects.create_user(
        "alice@test.com",
        "alice@test.com",
        "local-test-password",
    )
    category = Category.objects.create(name="Food")
    membership = WordCategory.objects.create(word=word, category=category)
    progress = UserWord.objects.create(
        user=learner,
        word=word,
        easy_streak=2,
        easy_count=3,
    )
    reporter_id = words["reporter"].id
    client = Client()
    client.force_login(admin)

    confirm = client.get(reverse("admin:api_word_archive", args=[word.pk]))
    assert confirm.status_code == 200
    assert "Archive" in confirm.content.decode()

    archived = client.post(reverse("admin:api_word_archive", args=[word.pk]))
    assert archived.status_code == 302
    word.refresh_from_db()
    assert word.archived_at is not None
    assert word.flagged_by_id == reporter_id

    restored = client.post(reverse("admin:api_word_restore", args=[word.pk]))
    assert restored.status_code == 302
    word.refresh_from_db()
    progress.refresh_from_db()
    membership.refresh_from_db()
    assert word.archived_at is None
    assert word.flagged_by_id == reporter_id
    assert progress.easy_streak == 2
    assert progress.easy_count == 3
    assert membership.category_id == category.pk
    logs = _change_logs_for(word)
    assert any("archived_at" in entry.change_message for entry in logs)


@pytest.mark.django_db
def test_bulk_archive_and_restore_selected_words() -> None:
    admin = _superuser()
    words = _seed_words()
    client = Client()
    client.force_login(admin)
    selected = [words["flagged"].pk, words["unflagged"].pk]

    confirm = client.post(
        CHANGE_LIST,
        {
            "action": "archive_selected",
            "_selected_action": selected,
        },
    )
    assert confirm.status_code == 200
    assert "Archive selected words" in confirm.content.decode()

    archived = client.post(
        CHANGE_LIST,
        {
            "action": "archive_selected",
            "_selected_action": selected,
            "post": "yes",
        },
    )
    assert archived.status_code == 302
    assert Word.objects.filter(pk__in=selected, archived_at__isnull=False).count() == 2

    restored = client.post(
        f"{CHANGE_LIST}?archive_status=archived",
        {
            "action": "restore_selected",
            "_selected_action": selected,
            "post": "yes",
        },
    )
    assert restored.status_code == 302
    assert Word.objects.filter(pk__in=selected, archived_at__isnull=True).count() == 2


@pytest.mark.django_db
def test_archive_requires_change_permission() -> None:
    viewer = _staff_with_word_view()
    words = _seed_words()
    client = Client()
    client.force_login(viewer)

    response = client.post(reverse("admin:api_word_archive", args=[words["flagged"].pk]))

    assert response.status_code == 403
    words["flagged"].refresh_from_db()
    assert words["flagged"].archived_at is None
