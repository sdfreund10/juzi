#!/usr/bin/env bash
# Idempotent release script for the production droplet.
# Run as the juzi user from /var/www/juzi (or set APP_DIR).
#
# Frontend: do not build here. CI (or an operator) syncs frontend/dist onto the
# box before or as part of deploy — see deploy/README.md.
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/juzi}"
BRANCH="${DEPLOY_BRANCH:-main}"
ENV_FILE="${ENV_FILE:-/etc/juzi.env}"

cd "$APP_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # Same file as systemd EnvironmentFile= (no shell expansion). Quote values
  # that contain $ or other shell metacharacters so source and systemd agree.
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

echo "==> Fetching ${BRANCH}"
git fetch --prune origin
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"

RELEASE="$(git rev-parse HEAD)"
if [[ -n "${EXPECTED_RELEASE:-}" && "$RELEASE" != "$EXPECTED_RELEASE" ]]; then
  echo "error: checkout does not match the frontend release; refusing to deploy." >&2
  exit 1
fi
# systemd reads this separately so every Gunicorn worker reports the deployed SHA.
printf 'SENTRY_RELEASE=%s\n' "$RELEASE" > "$APP_DIR/.sentry-release.env"
export SENTRY_RELEASE="$RELEASE"

echo "==> Syncing Python deps"
uv sync --locked --no-dev

if [[ ! -f frontend/dist/index.html ]]; then
  echo "error: frontend/dist/index.html missing." >&2
  echo "Sync a CI-built SPA to ${APP_DIR}/frontend/dist before deploying." >&2
  exit 1
fi

echo "==> Running migrations"
uv run python manage.py migrate --noinput

echo "==> Collecting static files"
uv run python manage.py collectstatic --noinput

echo "==> Restarting gunicorn"
# Prefer absolute path so this matches /etc/sudoers.d/juzi (NOPASSWD).
sudo "$(command -v systemctl)" restart juzi

echo "==> Health check"
sleep 1
curl -fsS "http://127.0.0.1:8000/api/health/" >/dev/null
echo "Deploy complete."
