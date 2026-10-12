# juzi

Django + PostgreSQL API with a [Preact](https://preactjs.com) (Vite) frontend.

Same-origin by default: Django + WhiteNoise serve the built SPA and `/api` together so session cookies work without CORS.

## Stack

| Layer | Tech |
| --- | --- |
| API | Django 6 + Django REST Framework |
| Static / SPA | WhiteNoise serving `frontend/dist` |
| DB | PostgreSQL |
| UI | Preact + TypeScript + Vite |
| Prod | gunicorn + nginx + certbot on a DO droplet |

```
juzi/
├── api/              # Django app
├── config/           # Django project settings
├── deploy/           # systemd, nginx, release script, runbook
├── manage.py
├── frontend/         # Preact + Vite
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.12+ and [uv](https://github.com/astral-sh/uv)
- Node.js `^20.19.0` or `>=22.12.0`
- PostgreSQL (local Postgres.app, Homebrew, or Docker)

## Quick start

### 1. Environment

```bash
cp .env.example .env
```

Defaults expect `DATABASE_URL=postgres://juzi:juzi@localhost:5432/juzi_development` and pytest DB `juzi_test`.

### 2. Database

**local Postgres**

```bash
createuser -s juzi 2>/dev/null || true
createdb -O juzi juzi_development 2>/dev/null || true
createdb -O juzi juzi_test 2>/dev/null || true
psql -d postgres -c "ALTER USER juzi WITH PASSWORD 'juzi' CREATEDB;"
```

Pytest uses `juzi_test` (`POSTGRES_TEST_DB`) and reuses it across runs (`--reuse-db`). Recreate the schema with `uv run pytest --create-db` when migrations change.

### 3. Build frontend + run Django (same origin)

```bash
cd frontend && npm install && npm run build && cd ..
uv sync
uv run python manage.py migrate
make seed-users   # DEBUG only: admin@test.com / ux-agent@test.com
uv run python manage.py collectstatic --noinput
uv run python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) — UI and API share one origin. Create additional study accounts in `/admin/` (Users → Add); the admin form treats username as email and writes both fields.

- Health: `GET /api/health/`
- Auth: `GET /api/auth/me/`, `POST /api/auth/login/`, `POST /api/auth/logout/` (email + password; session cookie)

### 4. Frontend watch build (optional, local only)

Keep Django running on `:8000`, then:

```bash
cd frontend
npm run dev
```

That runs `vite build --watch` in development mode and rewrites `frontend/dist` on each change, so WhiteNoise on [http://127.0.0.1:8000](http://127.0.0.1:8000) picks up updates (refresh the browser; no HMR). For Vite’s HMR server instead, use `npm run dev:hmr` on [http://localhost:5173](http://localhost:5173) (proxies `/api` to Django).

## Production

Bare-metal DigitalOcean droplet (Postgres on-box, nginx + certbot, gunicorn). See **[deploy/README.md](deploy/README.md)** for bootstrap and CD secrets.

Pushes to `main` build the SPA in GitHub Actions, rsync `frontend/dist` to the droplet, then run `deploy/deploy.sh`. The droplet does not need Node.js.

## Useful commands

```bash
# Tests
uv run pytest
npm --prefix frontend test

# Lint / format
uv run ruff check .
uv run ruff format .

# Django shell
uv run python manage.py shell

# Database migrations
make makemigrations
make migrate
make showmigrations

# Seed words and categories from prepped_cards.json (local file preferred)
uv run python scripts/download_hsk.py
uv run python scripts/build_card_data.py --levels 1,2,3
uv run scripts/prep_cards.py
make seed-hsk
# If the local file is unavailable, set HSK_PREPPED_CARDS_URL in .env

# Seed local login accounts (DEBUG only; refuses when DJANGO_DEBUG is false)
make seed-users

# Rebuild SPA after frontend changes (for Django-served mode)
cd frontend && npm run build
```
