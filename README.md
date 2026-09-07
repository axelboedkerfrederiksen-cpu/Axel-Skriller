# Axel-Skriller

This workspace contains the connected Pricegrid product plus one unrelated application:

- [`price-monitor/`](price-monitor/README.md) — FastAPI monitoring backend, scraper workers, and the shared PostgreSQL/Supabase data model.
- [`pricegrid-dashboard/`](pricegrid-dashboard/README.md) — customer-facing dashboard that reads live, customer-scoped data from Price Monitor.
- [`bill-tracker/`](bill-tracker/README.md) — in-memory bill tracker.

```text
competitor sites -> Price Monitor workers -> Supabase PostgreSQL
                                                |
                                                v
                                     Price Monitor FastAPI
                                                |
                                                v
                                      Pricegrid dashboard
```

The dashboard never connects directly to Supabase. Its server calls the protected FastAPI read
endpoints, so the database credentials and backend bearer token never reach the browser.
