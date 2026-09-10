# Tutorial: sådan bruger du Pricegrid

Denne tutorial viser den nuværende brugerrejse fra en frisk checkout til et fungerende
lokalt prisovervågningsflow. Den er skrevet til PowerShell på Windows. På macOS/Linux kan
`py -3.12` erstattes af `python3`, og `.venv\Scripts\...` af `.venv/bin/...`.

## 1. Forstå de to Pricegrid-brugerflader

Der er to forskellige webflader:

- **Price Monitor** på `http://127.0.0.1:8000/` er operator-workspace’et. Her opretter du
  kunder, konkurrenter og produkter, konfigurerer alerts og ser scraper health.
- **Pricegrid dashboard** er kundevisningen. Den viser pris-KPI’er, produkter,
  konkurrent-sammenligning og monitoring health. Den er read-only i forhold til backendens
  katalog.

Price Monitor-backenden er den autoritative kilde. Dashboardet kan først vise live-data,
når det er konfigureret med backendens URL og et customer UUID.

## 2. Installer Price Monitor lokalt

Åbn et PowerShell-vindue i repository-roden:

```powershell
Set-Location price-monitor
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Det installerer backendens runtime, testværktøjer, linter og type checker i projektets
virtuelle miljø.

## 3. Opret database og realistiske udviklingsdata

Den lokale standard er SQLite under `price-monitor/var/`. Initialiser først schemaet og seed
derefter det indbyggede Books to Scrape-eksempel:

```powershell
.\.venv\Scripts\price-monitor.exe init-db
.\.venv\Scripts\price-monitor.exe seed-development
```

Seed-kommandoen opretter blandt andet:

- kunden **Northline Goods**;
- konkurrenten **Books to Scrape**;
- produkterne *A Light in the Attic*, *Tipping the Velvet* og *The Secret Garden*;
- accepterede prisobservationer, en prisændring og en historik;
- et eksempel på en fejlet scrape, så health-visningen har noget at vise.

Seed-data må kun bruges i `development` eller `test`, og kommandoen blander ikke data ind i
en allerede udfyldt database.

## 4. Start operator-workspace’et

Start API’et i det første terminalvindue:

```powershell
.\.venv\Scripts\python.exe -m uvicorn price_monitor.main:app --reload
```

Åbn derefter:

- [`http://127.0.0.1:8000/`](http://127.0.0.1:8000/) for workspace’et
- [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs) for API-dokumentation
- [`http://127.0.0.1:8000/healthz`](http://127.0.0.1:8000/healthz) for liveness
- [`http://127.0.0.1:8000/readyz`](http://127.0.0.1:8000/readyz) for database readiness

I lokal development er API-token valgfrit. Hvis `PRICE_MONITOR_API_TOKEN` er sat, beder
workspace’et om access key ved login og gemmer den ikke i browseren.

## 5. Brug operator-workspace’et

### Overview

Overview viser de seneste accepterede priser, prisændringer og ting, der kræver attention.
En fejlet kontrol erstatter ikke den sidste trusted price; den markeres i stedet som
degraded/stale/failed.

### Tilføj en konkurrent

Gå til **Competitors** og vælg **Add competitor**.

1. Indtast et navn, f.eks. `Books to Scrape`.
2. Vælg en installeret trusted source adapter.
3. Indtast base URL for det samme hostname som adapteren tillader.
4. Vælg eventuelt forventet valuta.
5. Gem konkurrenten.

En konkurrent er en konfigureret kilde. Den bliver først overvåget, når et produkt er koblet
til en konkret produkt-URL.

### Tilføj et produkt og en konkurrent-URL

Gå til **Products → Add product**.

1. Indtast produktnavn og eventuelt SKU.
2. Indtast din egen pris og valuta, hvis produktet skal sammenlignes med egen pris.
3. Vælg en aktiv konkurrent.
4. Indtast konkurrentens produkt-URL.
5. Vælg **Add product**.

Systemet opretter produktet, kobler URL’en til konkurrenten og lægger den første kontrol i
køen. Produkt-URL’en skal bruge det hostname, der er konfigureret på konkurrenten; redirects,
private IP-adresser, credentials og uautoriserede hosts afvises.

### Kør en kontrol

En køet kontrol kræver en worker. Start derfor et nyt terminalvindue i `price-monitor`:

```powershell
.\.venv\Scripts\price-monitor.exe worker
```

Worker’en kører kontinuerligt. For en enkelt kontrol kan du bruge:

```powershell
.\.venv\Scripts\price-monitor.exe worker-once
```

Når en kontrol er accepteret, opdateres current offer og append-only price history. Ved
ændring kan du se gammel pris, ny pris, retning og tidspunkt på produktets detaljeside.

> Bemærk: en worker mod rigtige konkurrent-URL’er laver netværkskald. Brug den kun, når du
> faktisk vil hente live-sider. Den offline demo, der beskrives nedenfor, bruger fixture-filer.

### Start automatisk planlægning

I et separat terminalvindue kan du starte scheduler’en:

```powershell
.\.venv\Scripts\price-monitor.exe scheduler
```

Scheduler’en finder targets, der er due, og lægger dem i den PostgreSQL/SQLite-baserede kø.
Worker-processen henter derefter jobs fra køen. Kør normalt én scheduler og et kontrolleret
antal workers.

### Se produktdetaljer

Åbn et produkt fra **Products**. Her finder du:

- egen pris og aktuelle konkurrenttilbud;
- billigste tilbud og prisposition;
- lagerstatus og seneste trusted check;
- accepteret prisgraf;
- prisændringshistorik;
- knappen **Check now** til manuel køning;
- mulighed for at tilføje endnu en konkurrent-URL.

### Opret en alert

Gå til **Alerts** og opret en regel for et aktivt produkt:

1. vælg produkt;
2. vælg alle ændringer, prisstigninger eller prisfald;
3. angiv tærskel i procent;
4. vælg **Create alert**.

Alerts evalueres kun på accepterede prisobservationer efter regelens oprettelse. En fejlet
scrape ændrer ikke den trusted price og udløser ikke en alert. Alerts er i-app alerts; der
er endnu ingen e-mail-, SMS- eller webhook-levering.

### Se scraper health

På **Competitors** kan du se status pr. source, seneste succes og antal fejl. Statusserne
hjælper med at skelne mellem:

- normal/healthy monitoring;
- stale eller midlertidigt degraded monitoring;
- gentagne extraction-fejl, der kan føre til en repair task.

Transportfejl, 401/403, 429, CAPTCHA og robots-afvisning udløser ikke automatisk selector
repair. De behandles som fetch-/driftsproblemer.

## 6. Kør den komplette offline demo

Den hurtigste måde at se hele repair-flowet er:

```powershell
.\.venv\Scripts\price-monitor.exe demo
```

Demoen er netværksfri og demonstrerer:

1. en initial pris, der valideres og gemmes;
2. en prisændring, der gemmer den tidligere pris;
3. en ødelagt selector, der opretter en repair task;
4. en forkert kandidat, der afvises af fixture/evidence-checks;
5. en gyldig kandidat, der testes mod old, new og holdout pages;
6. eksplicit deployment af den validerede revision;
7. rollback-muligheden til den forrige adapterrevision.

Repair deployes aldrig automatisk af demoen. Den samme regel gælder den normale CLI:

```text
repair-once       valider/stag én repair, men deploy ikke
repair-worker     valider/stag repairs løbende
deploy-repair ID  deploy én eksplicit valideret revision
rollback ID       peg en konkurrent tilbage på tidligere revision
```

Hvis du vil se ét respektfuldt live-kald mod Books to Scrape, skal du selv opt-in:

```powershell
.\.venv\Scripts\price-monitor.exe live-smoke
```

## 7. Start Pricegrid dashboardet i demo mode

Åbn et nyt terminalvindue i repository-roden:

```powershell
Set-Location pricegrid-dashboard
npm install
npm run dev
```

Åbn den lokale URL, som Vite/Vinext viser. Uden ekstra konfiguration bruger dashboardet
demo-data fra `lib/mock/data.ts`.

Dashboardets navigation indeholder:

- **Overview** — samlede KPI’er, største prisgab og seneste events;
- **Products** — filtrerbare produkter med prisposition;
- **Products → et produkt** — tilbud, lagerstatus, events og pris-historik;
- **Competitors** — dækning, billigste produkter og success rate;
- **Monitoring** — freshness, stale checks og failed checks.

Mock-data er bevidst let at udforske og indeholder både healthy, stale og failed eksempler.
Banneret i UI’et viser, om du ser `Demo data` eller live-data.

## 8. Forbind dashboardet til den lokale backend

Først skal backend’en køre og have seed-data. Find customer UUID med:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/customers | ConvertTo-Json
```

Kopiér `id` fra kunden **Northline Goods**. Opret derefter dashboardets lokale miljøfil:

```powershell
Set-Location ..\pricegrid-dashboard
Copy-Item .env.example .env.local
```

Redigér `.env.local`:

```env
PRICEGRID_USE_MOCK_API=false
PRICE_MONITOR_API_BASE_URL=http://127.0.0.1:8000
PRICE_MONITOR_CUSTOMER_ID=<customer-uuid-fra-api>
# Kun nødvendig hvis backend’en bruger token:
# PRICE_MONITOR_API_TOKEN=<samme-token-som-backenden>
```

Genstart dashboardets udviklingsserver. Dashboardet kalder nu backendens customer-scoped
read endpoints på serveren. Token og database credentials sendes ikke til browseren.

Hvis du vil gå tilbage til demo-data, sæt `PRICEGRID_USE_MOCK_API=true` eller fjern
`.env.local` og genstart serveren.

## 9. Brug den separate bill tracker

Bill tracker er ikke en del af Pricegrid-flowet, men kan køres sådan:

```powershell
Set-Location ..\bill-tracker
pnpm install
pnpm dev --host 127.0.0.1
```

I appen kan du:

1. skrive payee/description;
2. indtaste beløb i USD;
3. vælge due date;
4. vælge `Paid` eller `Unpaid`;
5. trykke **Add bill**;
6. skifte status med **Mark paid** eller **Mark unpaid**.

Regninger sorteres efter tidligste due date. Data ligger kun i browserens aktuelle session og
forsvinder ved refresh eller lukning af siden.

## 10. Kontroller at ændringer stadig virker

Price Monitor:

```powershell
Set-Location ..\price-monitor
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m mypy src/price_monitor
```

Dashboard:

```powershell
Set-Location ..\pricegrid-dashboard
npm run lint
npx tsc --noEmit
npm run build
```

Bill tracker:

```powershell
Set-Location ..\bill-tracker
pnpm test
pnpm typecheck
pnpm build
```

## 11. Hvad er næste naturlige skridt?

Den nuværende beta er klar til lokal gennemgang og kontrolleret backend-integration. Før en
bred produktion bør projektet især få:

- durable storage til HTML-artifacts og adapter revisions;
- per-customer accounts, roller og audit events;
- flere rigtige konkurrent-adapters og større regression corpus;
- metrics for queue age, stale leases, repair rate og request budgets;
- notification delivery for alerts.

Se [price-monitor/README.md](price-monitor/README.md) og
[price-monitor/docs/architecture.md](price-monitor/docs/architecture.md) for den fulde
deployment- og sikkerhedsbeskrivelse.
