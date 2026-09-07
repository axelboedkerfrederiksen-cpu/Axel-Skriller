# Architecture and trust boundaries

## Shape

The beta is a modular monolith packaged once and run with separate API, scheduler,
scrape-worker, and repair-executor commands. PostgreSQL is the system of record and the
durable work queue. This avoids Redis, Celery, and service sprawl while retaining clear
module boundaries that can be split later.

```text
Pricegrid browser -> dashboard server -> FastAPI read API
                                            |
                                            v
API / scheduler ----------------> PostgreSQL / Supabase <----- scrape worker
                                                                  |
                                                          trusted fetch policy
                                                                  |
                                                     site adapter (extraction)
                                                                  |
                                                      validation + history
                                                                  |
                                                        health / repair task
                                                                  |
                                                     isolated repair executor
                                                                  |
                                                     deterministic reviewer
                                                                  |
                                                     version pointer / rollback
```

No database transaction is held while making a network request, rendering a browser
page, calling a repair provider, or executing candidate tests.

## Dashboard boundary

The dashboard never connects to PostgreSQL or Supabase from the browser. Server Components call
customer-scoped FastAPI read endpoints with the deployment bearer token, then send only rendered
UI data to the browser. The token and database connection strings are server-only environment
variables and must never use a public frontend prefix.

The current bearer token authenticates the deployment, not an individual customer. A configured
dashboard deployment is therefore pinned to one customer UUID. Per-user authentication and
authorization must be added before one deployment can safely switch between customer accounts.

## Deterministic path

Routine scraping never calls an LLM. A site adapter declares either `http` or `browser`
fetch mode and extracts structured values plus field-level evidence from an immutable
page snapshot. The trusted validator independently checks schema, price bounds,
currency, identity, URL host, selector evidence, and suspicious temporal changes.

Every attempt is retained in `scrape_results`. Only accepted results enter append-only
`price_history`; previous price and change are computed in the final database
transaction. Unchanged observations remain useful freshness evidence.

## Failure classification

Transport errors, 401/403, 429, CAPTCHA signals, and a single missing product do not
trigger code repair. They cause retry/backoff or an operator-visible degraded state.
Repeated extraction, schema, identity, or plausibility failures can create one
deduplicated repair task per competitor/revision/signature.

## Repair boundary

The automatically repairable surface is a typed, adapter-owned selector specification.
It cannot change fetching, validation, persistence, tests, or deployment policy. Custom
Python adapters are supported by the extraction contract but require human code review.

A candidate is treated as untrusted. It is checked for schema and scope, run without
network against known-good, newly-failing, and holdout pages, and its JSON result is
validated again in the trusted parent. Passing code execution alone is not acceptance.
Promotion writes an immutable revision and atomically changes a small active-version
manifest; the prior revision is retained for rollback.

The bundled subprocess runner is a development convenience, not a security boundary.
Production repair execution must happen in a separate worker or CI runner with no
secrets or network and with a read-only root, non-root UID, dropped capabilities,
`no-new-privileges`, PID/CPU/memory/output/time limits, and writable scratch only. The
API service must never receive a Docker socket.

## Responsible fetching and SSRF controls

Fetches are limited to the exact hostname configured for a competitor. Schemes,
credentials, ports, DNS results, and every redirect are checked; private, loopback,
link-local, multicast, reserved, and unspecified addresses are rejected. Responses are
bounded by content type and bytes. Requests use a descriptive user agent, per-host
delays, timeouts, and limited backoff. Browser rendering is never a silent fallback.
The system does not bypass logins, CAPTCHAs, robots exclusions, or anti-bot controls.

DNS validation before a connection reduces SSRF risk but is not a complete defense
against DNS rebinding in every HTTP stack. Production should additionally enforce an
egress proxy/firewall that only permits approved public destinations.

## AI boundary

An optional repair provider may diagnose snapshots and propose a selector spec, and an
optional matcher may help with ambiguous products. Scraped HTML is untrusted input and
must not be allowed to issue instructions or reach secrets/tools. Scheduling, fetching,
extraction, validation, history, repair acceptance, promotion, and rollback remain
deterministic and work with AI disabled.

The bundled OpenAI provider uses a strict structured-output schema and has no tools. Before
an opt-in request, it removes executable/embedded elements and all but a small selector-useful
attribute allowlist, then truncates each snapshot. Its output can only add selector rules to
the fields implicated by the failure. The deterministic parent process reconstructs the full
candidate while preserving every old selector, then applies the same policy and fixture gate.
