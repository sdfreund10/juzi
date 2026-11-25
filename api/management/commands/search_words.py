from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from api.services.embeddings import COMMAND_TIMEOUT, EmbeddingFailed, embed_texts, rank_words


class Command(BaseCommand):
    help = "Cosine-search stored word embeddings for one prompt."

    def add_arguments(self, parser):
        parser.add_argument("prompt", help="Text to embed and compare with stored words.")
        parser.add_argument(
            "--limit",
            type=int,
            default=8,
            help="How many matches to print (default 8).",
        )

    def handle(self, *args, **options):
        prompt = options["prompt"].strip()
        if not prompt:
            raise CommandError("Prompt is empty.")
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be a positive count.")

        try:
            query = embed_texts([prompt], timeout=COMMAND_TIMEOUT)[0]
        except EmbeddingFailed as exc:
            raise CommandError(str(exc)) from exc

        matches = rank_words(query, limit=limit)
        if not matches:
            self.stdout.write("No matching words.")
            return
        for score, word in matches:
            self.stdout.write(f"{score:.3f}\t{word.chinese}\t{word.pinyin}\t{word.english_basic}")
