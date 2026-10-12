# Sentry

Frontend and backend report to separate Sentry projects. Missing DSNs disable
reporting. Sampling is defined in code: 100% in production, 0% in development.
Backend environment follows `DJANGO_DEBUG`; frontend environment follows Vite mode.

## GitHub Actions

Set these **repository** variables/secrets (the frontend job runs outside the
`production` deployment environment):

- Variable `VITE_SENTRY_DSN`: frontend project DSN.
- Variable `SENTRY_ORG`: organization slug.
- Secret `SENTRY_AUTH_TOKEN`: organization source-map upload token (`org:ci`).

CI builds use project `juzi-frontend` and the commit SHA as the release. Configured
release builds require successful source-map uploads; maps are removed before
deployment. PR builds do not receive Sentry configuration or upload credentials.

## Droplet

Set `SENTRY_DSN` to the backend project DSN in `/etc/juzi.env`.
Install the updated `deploy/juzi.service` and run `sudo systemctl daemon-reload`.
The release script writes `.sentry-release.env`, which the unit reads to set
`SENTRY_RELEASE` to the deployed commit SHA.

For local error reporting, put `SENTRY_DSN` in the root `.env` and
`VITE_SENTRY_DSN` in `frontend/.env.local`. Tracing stays disabled in development.
