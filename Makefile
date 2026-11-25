.PHONY: makemigrations migrate showmigrations seed-hsk seed-users embed-words

makemigrations:
	uv run python manage.py makemigrations

migrate:
	uv run python manage.py migrate

showmigrations:
	uv run python manage.py showmigrations

seed-hsk:
	uv run python manage.py seed_hsk

embed-words:
	uv run python manage.py embed_words

seed-users:
	uv run python manage.py seed_users
