from django.conf import settings
from django.db import models
from django.utils import timezone


class WordQuerySet(models.QuerySet):
    def active(self):
        """Words that still show up in practice.

        The default manager stays unfiltered so admin and imports can still
        find archived rows.
        """
        return self.filter(archived_at__isnull=True)


class Word(models.Model):
    """Vocabulary entry: traditional Chinese, pinyin with tone marks, and basic English."""

    chinese = models.CharField(max_length=64)
    simplified = models.CharField(max_length=64, blank=True, default="")
    pinyin = models.CharField(max_length=128)
    english_basic = models.CharField(max_length=255)
    hsk_level = models.IntegerField(default=0)
    example_sentence_traditional = models.CharField(max_length=255, blank=True, default="")
    example_sentence_simplified = models.CharField(max_length=255, blank=True, default="")
    example_sentence_pinyin = models.CharField(max_length=255, blank=True, default="")
    example_sentence_english = models.CharField(max_length=255, blank=True, default="")
    flagged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flagged_words",
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, this word is hidden from practice. Progress, decks, and flags stay.",
    )

    objects = WordQuerySet.as_manager()

    class Meta:
        ordering = ["chinese"]

    def __str__(self) -> str:
        return self.chinese

    def archive(self) -> None:
        """Hide this word from practice. A second call leaves the original stamp."""
        if self.archived_at is not None:
            return
        self.archived_at = timezone.now()
        self.save(update_fields=["archived_at"])

    def restore(self) -> None:
        """Return this word to practice. Flags, decks, and progress stay as they are."""
        if self.archived_at is None:
            return
        self.archived_at = None
        self.save(update_fields=["archived_at"])


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
    """Per-user practice state for a vocabulary word (all quiz modes share one row)."""

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
    easy_streak = models.PositiveIntegerField(default=0)
    easy_count = models.PositiveIntegerField(default=0)
    due_on = models.DateField(null=True, blank=True)
    last_practiced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "word"],
                name="uniq_userword_user_word",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "due_on"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.word_id}"


class Learner(models.Model):
    """Per-user learner state."""

    class ProficiencyLevel(models.TextChoices):
        NOVICE = "novice", "Novice"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        EXPERT = "expert", "Expert"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learner",
    )
    proficiency_level = models.CharField(
        max_length=20,
        choices=ProficiencyLevel.choices,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"{self.user_id}:{self.proficiency_level or 'unset'}"
