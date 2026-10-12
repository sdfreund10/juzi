# Sentry setup and verification

Sentry projects are provisioned in the `steve-freund` organization:

- [juzi-frontend](https://steve-freund.sentry.io/issues/?project=4512244696809472)
  DSN: `https://98d021aaf0afdde60bc725b76e6a9993@o162182.ingest.us.sentry.io/4512244696809472`
- [juzi-backend](https://steve-freund.sentry.io/issues/?project=4512244696940544)
  DSN: `https://903b12f42c1258a93b059f3b487538b2@o162182.ingest.us.sentry.io/4512244696940544`

DSNs are ingestion identifiers. The source-map upload authentication token is private.

## Activate production

1. Create an organization source-map upload token in Sentry, scoped to `org:ci`,
   and save it as the **repository** GitHub Actions secret `SENTRY_AUTH_TOKEN`.
   The frontend job runs before the `production` deployment environment; putting
   this secret only in that environment will not make it available to the build.
2. Set repository Actions variables `SENTRY_ORG=steve-freund` and
   `VITE_SENTRY_DSN` to the frontend DSN above. Optionally set
   `VITE_SENTRY_TRACES_SAMPLE_RATE`; it defaults to `1`.
3. Add these values to `/etc/juzi.env` on the droplet:

   ```dotenv
   SENTRY_DSN=https://903b12f42c1258a93b059f3b487538b2@o162182.ingest.us.sentry.io/4512244696940544
   SENTRY_ENVIRONMENT=production
   SENTRY_TRACES_SAMPLE_RATE=1
   ```

4. Install the updated unit with `sudo cp /var/www/juzi/deploy/juzi.service
   /etc/systemd/system/juzi.service` and `sudo systemctl daemon-reload`.
   The release script writes `.sentry-release.env`; the unit reads it to give
   Gunicorn the same Git SHA as the frontend build. Management commands use the
   SHA exported by the release script.
5. Deploy through the existing main-branch workflow. With a configured frontend
   DSN, missing upload credentials or failed source-map uploads fail the build.
   Source maps are uploaded privately and removed before artifact storage.
   PR builds receive no Sentry configuration or credentials.

Without DSNs the SDKs stay disabled. Keep local `.env` DSNs blank and omit
`frontend/.env.local` to avoid reporting development/test events. To explicitly
exercise development reporting, put backend values in the root `.env` and
`VITE_SENTRY_*` values in `frontend/.env.local`, with environment `development`.
Vite does not load the root `.env`.

## Alerts already configured

All monitors filter to `production`, count actual observations in a rolling hour,
fire at three or more slow observations, and resolve below three:

- [Slow page loads](https://steve-freund.sentry.io/monitors/10618334/):
  `is_transaction:true span.op:pageload span.duration:>4000`.
- [Slow session starts](https://steve-freund.sentry.io/monitors/10618494/):
  `is_transaction:true span.op:study.session_ready span.duration:>3000 study.outcome:ready`.
- [Slow API requests](https://steve-freund.sentry.io/monitors/10618495/):
  `span.op:http.client span.duration:>2000` in the frontend project.
  Browser HTTP instrumentation includes only same-origin `/api/` calls and
  excludes `/api/health/`, so telemetry and health calls are not counted.

[Slowdown and recovery notifications](https://steve-freund.sentry.io/monitors/alerts/6156875/)
email the `steve-freund` team on first occurrence, regression, and resolution.
[New and regressed error notifications](https://steve-freund.sentry.io/monitors/alerts/6156871/)
cover both projects. The two default high-priority notification rules created
with these projects were disabled to avoid duplicate email. Notification repeat intervals are zero because triggers
are state changes, not every observation. Team delivery includes the account
owner; check personal email notification preferences in Sentry.

Sentry accepted these monitors on the current account without upgrading it.
The MCP interface does not expose the billing subscription or evaluation cadence;
verify continued entitlement after any trial and choose a five-minute cadence
in the UI if offered. Do not activate a paid subscription automatically.

Page-load duration measures the Sentry pageload transaction, rather than LCP.
Session-ready timing begins at Start studying (or mounting a bookmarked session)
and ends after the first card DOM is committed. Empty, failed, and cancelled
attempts are tagged separately and excluded from the successful-session alert.
Browser navigation and fetch tracing connect requests to Django traces.

## Privacy and quota

Error collection is unsampled and both trace rates start at 100%. Reduce the
trace rates if the household exceeds the account allowance; count-based alerts
then see only sampled observations. Check Sentry quotas before activating.
Replay and profiling are not enabled. No user identification, request bodies,
headers, cookies, query parameters, database bound values, or stack-frame locals
are intentionally collected. Console breadcrumbs are disabled. API errors use
stable messages, method, pathname, and status instead of response text or bodies.
Exceptions themselves should never contain credentials or private study content.

## Manual frontend release

From a trusted shell with `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `VITE_SENTRY_DSN`
set, build the exact checkout that will be deployed:

```bash
export SENTRY_PROJECT=juzi-frontend
export SENTRY_UPLOAD=true
export VITE_SENTRY_ENVIRONMENT=production
export VITE_SENTRY_RELEASE="$(git rev-parse HEAD)"
export VITE_SENTRY_TRACES_SAMPLE_RATE=1
npm --prefix frontend ci
npm --prefix frontend run build
```

Sync `frontend/dist` as described in the deployment runbook, then run the release
script with `EXPECTED_RELEASE` set to that same SHA. It refuses mismatched code.
Never prefix the upload token with `VITE_`; Vite exposes those variables publicly.

## Live acceptance checks

After activation, use a controlled development instance with the production
build and a distinct verification release; never add public crash endpoints.

1. Capture one controlled browser exception; confirm original TypeScript source
   locations resolve using the uploaded maps.
2. Capture one controlled backend exception and verify environment/release tags.
3. Start a study session and inspect its `study.session_ready` span, API child
   span, and Django trace. Verify both sides share the trace ID.
4. Use browser network throttling to create three slow page loads, three slow
   session starts, and three slow API requests. Confirm the relevant monitors
   fire and email arrives; return to normal speed and confirm recovery once the
   rolling-hour count falls below three. Remove verification events afterward.
5. Verify login validation errors do not create issues and request payloads,
   cookies, account emails, and study content are absent from captured events.
6. Confirm the deploy artifact has no `.map` files and no upload token.

Project/alert creation has been verified. Source-map upload, deployed ingestion,
trace correlation, actual email delivery, and recovery require production
credentials/configuration and are not implied by passing local tests.
