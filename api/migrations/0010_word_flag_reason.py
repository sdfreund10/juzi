from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0009_word_archived_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="word",
            name="flag_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("wrong_deck", "Wrong deck"),
                    ("bad_translation", "Bad translation"),
                    ("bad_example", "Bad example"),
                    ("other", "Other"),
                ],
                default="",
                max_length=32,
            ),
        ),
    ]
