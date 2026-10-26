import pytest
from django.db import IntegrityError, transaction

from api.models import Word, WordEmbedding


@pytest.fixture
def word(db) -> Word:
    return Word.objects.create(chinese="字", pinyin="zì", english_basic="character")


def test_word_has_one_embedding(word: Word) -> None:
    embedding = WordEmbedding.objects.create(
        word=word,
        model_name="test-embedding-model",
        source_text="Chinese: 字\nMeaning: character",
        vector=[0.25, -0.5, 0.75],
    )
    embedding.refresh_from_db()
    assert word.embedding == embedding
    assert embedding.vector == [0.25, -0.5, 0.75]
    assert embedding.source_text == "Chinese: 字\nMeaning: character"

    with pytest.raises(IntegrityError), transaction.atomic():
        WordEmbedding.objects.create(
            word=word,
            model_name="another-model",
            source_text="character",
            vector=[0.1, 0.2],
        )


def test_deleting_word_removes_its_embedding(word: Word) -> None:
    embedding = WordEmbedding.objects.create(
        word=word,
        model_name="test-embedding-model",
        source_text="Chinese: 字\nMeaning: character",
        vector=[0.25, -0.5, 0.75],
    )

    word.delete()

    assert not WordEmbedding.objects.filter(pk=embedding.pk).exists()
