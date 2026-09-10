# Axel-Skriller / Pricegrid

Dette repository indeholder den nuværende Pricegrid-beta: et system til at overvåge
konkurrenters priser, gemme godkendte prisobservationer og vise dem i et dashboard.

Der er tre selvstændige dele:

| Mappe | Hvad den indeholder |
| --- | --- |
| [`price-monitor/`](price-monitor/README.md) | Python/FastAPI-backend, database, scraper-workers, operator-workspace, alerts og guarded repair-flow. |
| [`pricegrid-dashboard/`](pricegrid-dashboard/README.md) | Kundeorienteret React-dashboard med overblik, produkter, konkurrenter og monitoring health. |
| [`bill-tracker/`](bill-tracker/README.md) | Separat React-demo til registrering af regninger. Den bruger kun in-memory state og er ikke koblet til Pricegrid. |

## Sådan hænger Pricegrid sammen

```text
konkurrentsider
      │
      ▼
Price Monitor scheduler ──> scrape worker ──> validering ──> PostgreSQL/Supabase
                                                                     │
                                                                     ▼
                                                        Price Monitor API
                                                                     │
                                                                     ▼
                                                           Pricegrid dashboard
```

Dashboardet taler kun med FastAPI-backenden. Det får ikke direkte adgang til Supabase,
database credentials eller backend-token.

## Hurtig start

Den samlede gennemgang findes i [TUTORIAL.md](TUTORIAL.md). Den anbefalede rækkefølge er:

1. Kør den offline demo for at se scrape → prisændring → fejl → repair → rollback-flowet.
2. Start Price Monitor lokalt med SQLite og seedede fixture-data.
3. Åbn operator-workspace’et på `http://127.0.0.1:8000/`.
4. Start dashboardet i mock mode, eller forbind det til den lokale backend.

Offline demo:

```powershell
Set-Location price-monitor
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\price-monitor.exe demo
```

Dashboardet kan startes alene med demo-data:

```powershell
Set-Location pricegrid-dashboard
npm install
npm run dev
```

Åbn den URL, som udviklingsserveren viser. Dashboardet bruger mock-data som standard.

## Dokumentation

- [Tutorial: brug systemet fra start til slut](TUTORIAL.md)
- [Price Monitor README](price-monitor/README.md) — API, deployment, Supabase, CLI og arkitektur
- [Trust boundaries og sikkerhedsarkitektur](price-monitor/docs/architecture.md)
- [Pricegrid dashboard README](pricegrid-dashboard/README.md)
- [Bill tracker README](bill-tracker/README.md)

## Nuværende beta-grænser

- Lokal udvikling bruger SQLite; produktion er designet til PostgreSQL/Supabase.
- Dashboardet starter i mock mode og skal eksplicit sættes til live mode.
- Alerts vises i operator-workspace’et, men sender endnu ikke e-mail, SMS eller webhooks.
- Repair deployment er bevidst CLI-only og kræver en eksplicit deploy-kommando.
- Bill tracker er et separat eksempelprojekt uden database, login eller persistence.
