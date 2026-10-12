from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0004_userword_one_per_word"),
    ]

    operations = [
        migrations.AddField(
            model_name="word",
            name="example_sentence_english",
            field=models.CharField(default="", max_length=255),
        ),
        migrations.AddField(
            model_name="word",
            name="example_sentence_pinyin",
            field=models.CharField(default="", max_length=255),
        ),
        migrations.AddField(
            model_name="word",
            name="example_sentence_simplified",
            field=models.CharField(default="", max_length=255),
        ),
        migrations.AddField(
            model_name="word",
            name="example_sentence_traditional",
            field=models.CharField(default="", max_length=255),
        ),
    ]
