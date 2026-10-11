from django.db import migrations, models


def collapse_user_words(apps, schema_editor):
    """Keep one row per (user, word); sum easy_count, keep max streak / earliest due."""
    UserWord = apps.get_model("api", "UserWord")
    seen: dict[tuple[int, int], object] = {}
    for row in UserWord.objects.order_by("id").iterator():
        key = (row.user_id, row.word_id)
        existing = seen.get(key)
        if existing is None:
            seen[key] = row
            continue
        existing.easy_count += row.easy_count
        existing.easy_streak = max(existing.easy_streak, row.easy_streak)
        if row.due_on is not None and (
            existing.due_on is None or row.due_on < existing.due_on
        ):
            existing.due_on = row.due_on
        if row.last_practiced_at is not None and (
            existing.last_practiced_at is None
            or row.last_practiced_at > existing.last_practiced_at
        ):
            existing.last_practiced_at = row.last_practiced_at
        existing.save(
            update_fields=[
                "easy_count",
                "easy_streak",
                "due_on",
                "last_practiced_at",
            ]
        )
        row.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0003_word_hsk_level"),
    ]

    operations = [
        migrations.RunPython(collapse_user_words, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="userword",
            name="uniq_userword_user_word_mode",
        ),
        migrations.RemoveField(
            model_name="userword",
            name="mode",
        ),
        migrations.AddConstraint(
            model_name="userword",
            constraint=models.UniqueConstraint(
                fields=("user", "word"),
                name="uniq_userword_user_word",
            ),
        ),
    ]
