from django.conf import settings
from django.db import models


class Word(models.Model):
    """Vocabulary entry: traditional Chinese, pinyin with tone marks, and basic English."""

    chinese = models.CharField(max_length=64)
    simplified = models.CharField(max_length=64, default="")
    pinyin = models.CharField(max_length=128)
    english_basic = models.CharField(max_length=255)
    hsk_level = models.IntegerField(default=0)
    # Future enhancement: add example sentences for the word.
    # example_sentence_traditional = models.CharField(max_length=255, default="")
    # example_sentence_simplified = models.CharField(max_length=255, default="")
    # example_sentence_pinyin = models.CharField(max_length=255, default="")
    # example_sentence_english = models.CharField(max_length=255, default="")

    class Meta:
        ordering = ["chinese"]

    def __str__(self) -> str:
        return self.chinese


class Category(models.Model):
    """Named deck of words."""

    name = models.CharField(max_length=100, unique=True)
    words = models.ManyToManyField(
        Word,
        through="WordCategory",
        related_name="categories",
        blank=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class WordCategory(models.Model):
    """Join table between words and categories (decks)."""

    word = models.ForeignKey(Word, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    class Meta:
        db_table = "word_category"
        constraints = [
            models.UniqueConstraint(
                fields=["word", "category"],
                name="uniq_word_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category_id}:{self.word_id}"


class UserWord(models.Model):
    """Per-user practice state for a word in a specific quiz mode."""

    class Mode(models.TextChoices):
        PINYIN_TO_EN = "pinyin_to_en", "Pinyin to English"
        EN_TO_ZH = "en_to_zh", "English to Chinese"
        ZH_TO_EN = "zh_to_en", "Chinese to English"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_words",
    )
    word = models.ForeignKey(
        Word,
        on_delete=models.CASCADE,
        related_name="user_words",
    )
    mode = models.CharField(max_length=20, choices=Mode.choices)
    easy_streak = models.PositiveIntegerField(default=0)
    easy_count = models.PositiveIntegerField(default=0)
    due_on = models.DateField(null=True, blank=True)
    last_practiced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "word", "mode"],
                name="uniq_userword_user_word_mode",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "due_on"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.word_id}:{self.mode}"
