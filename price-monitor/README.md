# Price Monitor beta

A production-oriented beta for monitoring competitor product prices. It uses deterministic
scrapers for routine work, retains an auditable history, detects unhealthy adapters, and
puts every proposed repair through a tightly scoped test-and-review gate. A compact operator
workspace turns that trusted data into the daily product, offer, health, and alert workflow.

The existing `bill-tracker/` project is unrelated and remains untouched. This service is a
standalone Python application in `price-monitor/`.

## What is included

- FastAPI catalog and monitoring API
- Customer-scoped read API shaped for the Pricegrid dashboard
- PostgreSQL schema, SQLAlchemy 2 models, and Alembic migration
- Durable PostgreSQL-backed scheduling queue with worker leases
- Per-site, versioned adapter modules and declarative selector specs
- HTTP-first fetching with explicit opt-in Playwright support
- Exact-host and public-IP checks, bounded responses, retries, delays, robots.txt,
  CAPTCHA/interstitial classification, and no browser fallback
- Deterministic validation of money, currency, product identity, price bounds, temporal
  changes, and field-level extraction evidence
- Immutable scrape attempts, append-only accepted price history, and cached current offers
- A responsive operational workspace for overview, products, offer comparison, competitors,
  scraper health, and in-app price alerts
- Safe, compact monitoring-status endpoints for the UI that omit diagnostic messages and
  artifact locations
- Health tracking, failure classification, diagnostic HTML snapshots, and deduplicated
  repair tasks
- Guarded selector repair with immutable versions, old/new/holdout tests, explicit
  deployment, and atomic rollback pointers
- A complete offline demonstration plus an opt-in public live smoke check

Billing, end-user accounts, outbound alert delivery, automatic discovery/repricing, and a large
AI pricing system are intentionally outside this beta. Hosted access uses one deployment-level
operator token; it is not multi-user authentication.

## Architecture

The application is a modular monolith packaged once and run as separate API, scheduler,
scrape-worker, and repair-worker processes. PostgreSQL is both the system of record and
the small durable queue, avoiding Redis/Celery and microservice overhead at this stage.

```text
competitor sites -> scrape worker -> validation -> PostgreSQL / Supabase
                                              |                 |
                                              v                 v
                                   health + repair flow    FastAPI read API
                                                                |
                                                                v
                                                     Pricegrid dashboard

scheduler ---------------------> durable scrape queue
```

Network, browser, repair-provider, and candidate-test work happens outside database
transactions. The final result/history/health update is short, lease-checked, and atomic.
See [the trust-boundary document](docs/architecture.md) for the detailed design and risks.

## AI versus deterministic code

Routine fetching, parsing, validation, change detection, scheduling, history, acceptance,
deployment, and rollback do not use an LLM. The normal path works with AI disabled.

`RepairProvider` is the narrow extension point for an AI repair agent. Its input can include
the affected adapter spec, sanitized failure details, new HTML, known-good HTML, and the
fixture manifest. Its output is data: a typed site spec, never an executable Python patch.
The deterministic parent process still decides acceptance. A deterministic provider is
included for common selector changes, and manual candidates pass through the same gate.
The existing `MatchMethod.AI` boundary also leaves room for difficult product matching
without coupling normal monitoring to a model.

An opt-in OpenAI Structured Outputs provider is included. It removes scripts, comments,
iframes, and unnecessary attributes from snapshots, treats all retained HTML as untrusted,
has no tools, and can only return typed selector additions. Install and enable it explicitly:

```sh
.venv/bin/python -m pip install -e '.[ai]'
export PRICE_MONITOR_REPAIR_PROVIDER=openai
export PRICE_MONITOR_OPENAI_REPAIR_MODEL=your-enabled-model-id
export PRICE_MONITOR_OPENAI_API_KEY=replace-me
```

Model output never bypasses the local scope policy, isolated old/new/holdout tests, manual
deployment command, or rollback path. The default provider remains deterministic and makes
no external AI calls.

## Quick start

Requires Python 3.12 or newer.

```sh
cd price-monitor
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/price-monitor init-db
.venv/bin/uvicorn price_monitor.main:app --reload
```

The no-configuration local default is SQLite for developer convenience. Open
`http://127.0.0.1:8000/` for the operational workspace or `http://127.0.0.1:8000/docs` for the
API documentation. SQLite is not the production store.

The workspace is organized around these routes:

```text
/                         overview, price changes, and items needing attention
/products                 monitored products
/products/new             add a product and its first competitor URL
/products/{product_id}    trusted offers, history, and manual checks for one product
/competitors              configured sources and scraper health
/alerts                    create and manage in-app price-change rules
```

An empty database starts with a short workspace setup form. For a realistic offline development
workspace, apply migrations to an empty database and explicitly seed it:

```sh
.venv/bin/price-monitor seed-development
```

The command uses bundled fixtures and the real validation/result pipeline. It is idempotent for
its completed seed, refuses to mix seed records into a non-empty database, and is allowed only in
`development` or `test`. To run the same seed once during local app startup, set
`PRICE_MONITOR_SEED_DEVELOPMENT_DATA=true`. That setting is rejected in `preview` and
`production`, so development records cannot be enabled on a hosted deployment.

When `PRICE_MONITOR_API_TOKEN` is configured, the workspace asks for the access key. The key is
checked once and exchanged for a signed, 12-hour HttpOnly browser session; the page
does not retain the key. The cookie uses `SameSite=Strict`; hosted sessions are also marked
Secure, and UI mutations require a
same-origin request marker. Signing out clears the session cookie.

Direct API clients continue to send the deployment token to every `/api/v1` route:

```sh
curl -H "Authorization: Bearer $PRICE_MONITOR_API_TOKEN" \
  http://127.0.0.1:8000/api/v1/customers
```

Liveness and readiness probes remain available at `/healthz` and `/readyz` without the token.

Run checks:

```sh
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src/price_monitor
```

## Complete deterministic demo

```sh
.venv/bin/price-monitor demo
```

The demo uses immutable, sanitized copies of two pages from Books to Scrape so CI never
depends on the public network. It proves:

1. a £51.77 observation is validated and stored;
2. £47.99 is stored with £51.77 as the previous price and classified as a decrease;
3. a renamed price selector fails and creates a repair task with the HTML snapshot;
4. a wrong selector candidate executes but fails the fixture/evidence checks and is rejected;
5. a scoped candidate is tested in a separate process across old, new, and holdout pages;
6. the validated version is explicitly deployed and successfully scrapes the changed page;
7. the prior adapter revision remains available for immediate rollback.

The public URLs used by the demo adapter are recorded in
[`examples/books-to-scrape-catalog.json`](examples/books-to-scrape-catalog.json).
To opt in to a real request against that scraping sandbox:

```sh
.venv/bin/price-monitor live-smoke
```

Live access is never part of the automated suite.

## PostgreSQL with Docker Compose

Docker was not available in the build environment, so the Compose topology is provided but
was not executed here. Copy the example settings, replace the contact address and local
credentials, then start the durable services:

```sh
cp .env.example .env
docker compose up --build db migrate api scheduler worker
```

The API binds to `127.0.0.1:8000`. Production mode refuses to start without PostgreSQL and a
`PRICE_MONITOR_API_TOKEN` of at least 32 characters. Replace the placeholder database credentials
and generate a strong token before starting Compose.

The optional local repair worker uses development-only process isolation:

```sh
docker compose --profile development-repair up repair-worker
```

For production, set `PRICE_MONITOR_REPAIR_RUNNER_IMAGE` and run repair evaluation from a
separate executor or CI boundary. It needs no application secrets or network. Do not mount a
Docker socket into the API service.

## Supabase PostgreSQL

Supabase can replace the Compose PostgreSQL container without changing the application model.
It is the shared system of record for the API, scheduler, and workers; the dashboard still talks
to FastAPI and never receives a database password or Supabase service credential.

1. Create a Supabase project and open its **Connect** panel.
2. For Vercel, copy the Supavisor **Transaction pooler** URI on port 6543. For an always-on
   deployment, use the direct URI when IPv6 is available or the Session pooler on port 5432.
3. Change the URI scheme from `postgresql://` to `postgresql+psycopg://`, URL-encode special
   characters in the password, and append `?sslmode=require` if it is not already present.
4. Set `PRICE_MONITOR_DATABASE_URL` to that runtime URI.
5. Optionally set `PRICE_MONITOR_MIGRATION_DATABASE_URL` to Supabase's direct connection URI.
   `price-monitor init-db` and Alembic use this value while the running services keep using the
   pooled runtime URI.
6. Apply the schema once with `.venv/bin/price-monitor init-db`, then start the API, scheduler,
   and one or more controlled workers.

Do not use the transaction pooler URI for continuous worker processes. Because this service
uses direct PostgreSQL connections rather than the Supabase Data API, keep these tables out of an
exposed API schema or enable suitable RLS/grants before adding any browser-side Supabase access.
HTML artifacts and generated adapter revisions still need durable object storage in a hosted
deployment; only relational monitoring data is stored in Supabase by this integration.

## Vercel deployment boundary

Vercel hosts the FastAPI surface and runs a bounded monitoring batch every day at 06:00 UTC.
The thin root `app.py` entrypoint is configured in `pyproject.toml`; `vercel.json` defines the
scheduled call to `/api/cron/monitor` and keeps test/demo assets out of the Function bundle. Set
the Vercel project's Root Directory to `price-monitor`.

A short-lived CRUD/API preview can run with an explicitly disposable SQLite database under
`/tmp`:

```text
PRICE_MONITOR_ENVIRONMENT=preview
PRICE_MONITOR_DATABASE_URL=sqlite:////tmp/price-monitor-preview.db
PRICE_MONITOR_ARTIFACT_ROOT=/tmp/price-monitor/artifacts
PRICE_MONITOR_ADAPTER_RUNTIME_ROOT=/tmp/price-monitor/adapters
PRICE_MONITOR_EPHEMERAL_DEMO=true
PRICE_MONITOR_API_TOKEN=<at-least-32-random-characters>
CRON_SECRET=<a-different-at-least-32-random-characters>
```

This mode demonstrates the operational UI and HTTP catalog API, but it is not durable. Vercel's
`/tmp` filesystem is ephemeral and not shared between Function instances, so its catalog,
history, alert rules, artifacts, and repair revisions can vanish at any time. The UI can enqueue
a check, but temporary storage still makes results unreliable across Function instances. The app
rejects this mode when `PRICE_MONITOR_ENVIRONMENT=production`. Development seed data is also
rejected in preview mode.

For a real deployment, configure the Supabase transaction-pooler URL and apply Alembic migrations
as a separate release step. Each scheduled invocation queues due targets and processes at most
`PRICE_MONITOR_CRON_MAX_SCRAPES` (default `5`), so no infinite worker runs inside a Function. The
Hobby plan supports the configured daily schedule; more frequent checks require a Vercel plan that
supports more frequent cron jobs. Relational monitoring and alert data is durable in Supabase;
durable HTML artifact and repair-revision storage remains a later production hardening step.

Direct preview release, without a PR or CI publisher, requires Vercel CLI 48.8.0 or newer:

```sh
vercel link
vercel env add PRICE_MONITOR_ENVIRONMENT preview
# Add the remaining preview variables listed above.
vercel deploy
vercel inspect <preview-url> --logs
vercel curl /healthz --deployment <preview-url>
vercel curl /readyz --deployment <preview-url>
```

For production, stage with `vercel deploy --prod --skip-domain`, verify the generated URL, then
promote it with `vercel promote <staged-production-url>`. Keep the prior deployment URL available
for `vercel rollback`.

## Runtime commands

```text
price-monitor init-db                    apply migrations
price-monitor schedule-once              enqueue due targets once
price-monitor scheduler                  continuously enqueue due targets
price-monitor worker-once                process one scrape job
price-monitor worker                     continuously process scrape jobs
price-monitor repair-once                validate/stage one repair, never auto-deploy
price-monitor repair-worker              continuously validate/stage repairs
price-monitor deploy-repair REPAIR_ID     explicitly deploy a validated revision
price-monitor rollback COMPETITOR_ID      restore the previous adapter revision
price-monitor seed-development            seed one empty development/test database
price-monitor demo                        run the offline end-to-end proof
price-monitor live-smoke                  opt in to one public test-site request
```

## API surface

The versioned API provides customer, competitor, product, and product-mapping CRUD; manual
scrape queueing; result/history/offer reads; scraper health; in-app alert rules; and repair-task
reads. Catalog mutations use deactivation rather than destructive deletes.

Key routes include:

```text
POST /api/v1/customers
POST /api/v1/customers/{customer_id}/competitors
POST /api/v1/customers/{customer_id}/products
POST /api/v1/products/{product_id}/competitor-products
POST /api/v1/competitor-products/{target_id}/scrapes
GET  /api/v1/competitor-products/{target_id}/monitoring-status
GET  /api/v1/competitor-products/{target_id}/scrape-results
GET  /api/v1/products/{product_id}/price-history
GET  /api/v1/products/{product_id}/offers
GET  /api/v1/competitors/{competitor_id}/health
GET  /api/v1/competitors/{competitor_id}/health-summary
POST /api/v1/customers/{customer_id}/alert-rules
GET  /api/v1/customers/{customer_id}/alert-rules
PATCH /api/v1/alert-rules/{rule_id}
DELETE /api/v1/alert-rules/{rule_id}
GET  /api/v1/repair-attempts
GET  /api/v1/customers/{customer_id}/dashboard
GET  /api/v1/customers/{customer_id}/dashboard/products
GET  /api/v1/customers/{customer_id}/dashboard/products/{product_id}
GET  /api/v1/customers/{customer_id}/dashboard/competitors
GET  /api/v1/customers/{customer_id}/dashboard/health
```

The workspace uses `monitoring-status` and `health-summary` for routine state. These responses
contain only job state, timestamps, failure categories, and counters; they do not expose internal
failure messages, stack traces, diagnostic artifacts, or repair paths.

Alert rules support increase, decrease, or either-direction thresholds. Their displayed state is
derived from accepted price history recorded after the rule was created, so failed checks do not
replace the last trusted price or trigger a rule. Alerts are visible only inside this workspace;
email, webhook, SMS, and other notification delivery are not implemented.

Repair deployment is intentionally CLI-only until an authenticated admin boundary exists.
The API never accepts Python patches.

## Adding a competitor

Add one isolated module under `src/price_monitor/scrapers/sites/` and register its baseline
spec in `services/adapter_registry.py`. Prefer declarative selectors; implement the
`ScraperAdapter` protocol only when a site genuinely needs custom deterministic parsing.
Declare browser mode only for JavaScript-dependent pages. Install it explicitly with:

```sh
.venv/bin/python -m pip install -e '.[browser]'
.venv/bin/playwright install chromium
```

Every adapter should have saved pages covering normal, changed, absent, and misleading
prices. A repair corpus needs known-good, newly failing, and holdout cases before promotion.

## Important beta boundaries

- Use one scheduler and a controlled number of workers; rate limiting is process-local.
- DNS and redirect checks reduce SSRF risk, but hosted deployments should also enforce an
  outbound allowlist at the network/proxy layer to close DNS-rebinding gaps.
- Browser mode is more expensive and is never selected automatically.
- A 401/403/429, CAPTCHA, network error, or one missing product degrades health but does not
  trigger selector repair.
- The development subprocess runner is not a hostile-code sandbox. Automatic repair is
  limited to declarative specs; custom Python changes always require normal code review.
- A deployed repair remains in `repairing` state until a real scrape succeeds.

## Next priorities

1. Put immutable HTML artifacts and adapter revision files on durable hosted storage, then deploy
   the always-on scheduler and workers beside the Supabase-backed API.
2. Add per-customer accounts/roles and audit events before replacing the single operator token.
3. Add a second real competitor adapter and grow the old/new/holdout regression corpus.
4. Add operational metrics and alerts for queue age, stale leases, rejection rate, repair rate,
   and per-site request budgets.
5. Add customer onboarding and a safe way to keep each webshop's own prices synchronized.
6. Add notification delivery and acknowledgement workflows after operator identities and audit
   events provide the required security boundary.
