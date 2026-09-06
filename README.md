# Pricegrid dashboard

A customer-facing competitor price-monitoring dashboard built with Next.js-compatible Vinext, React, TypeScript, Tailwind CSS, and Recharts. It contains no scraper, database, authentication, or backend services.

## Included views

- Overview with pricing KPIs, recent events, largest gaps, and freshness status
- Sortable and filterable product comparison table with 24 demo products
- Product details with every competitor offer, stock status, event feed, and multi-series price history
- Competitor coverage, price position, and data health
- Customer-friendly monitoring and site health
- Responsive desktop and mobile navigation
- Loading, empty, not-found, and error states

## Run locally

Requirements: Node.js 22.13 or later.

```bash
npm install
npm run dev
```

Open the local URL shown in the terminal. For production validation:

```bash
npm run lint
npx tsc --noEmit
npm run build
```

## Frontend architecture

```text
app/                         Route pages and route-level states
components/                  Reusable dashboard components
components/products/         Product table and history chart
lib/api/                     Centralized backend boundary
lib/mock/                    Centralized demo dataset
lib/calculations.ts          Ranking, gap, freshness, and formatting utilities
lib/types.ts                 JSON-friendly application contracts
```

Pages and components never import the mock dataset directly. They call functions in `lib/api/`, which makes the mock implementation replaceable without changing the UI.

## Connect the FastAPI backend

1. Copy `.env.example` to `.env.local`.
2. Set `NEXT_PUBLIC_API_BASE_URL` to the public FastAPI origin.
3. Set `NEXT_PUBLIC_USE_MOCK_API=false`.
4. Return the documented JSON shapes from FastAPI, or add a small response mapper inside `lib/api/` if backend field names differ.
5. Allow the dashboard origin in FastAPI CORS settings.
6. Restart the frontend after changing environment variables.

Example:

```env
NEXT_PUBLIC_API_BASE_URL=https://pricing-api.example.com
NEXT_PUBLIC_USE_MOCK_API=false
```

All network requests are centralized in `lib/api/client.ts`. The product detail adapter intentionally combines the product detail and history endpoints, so the page still consumes a single `ProductDetailData` object.

## Expected backend endpoints

| Method | Endpoint | Expected response |
| --- | --- | --- |
| `GET` | `/api/dashboard` | `DashboardData` |
| `GET` | `/api/products` | `ProductComparison[]` |
| `GET` | `/api/products/{id}` | `{ comparison: ProductComparison, events: PriceChangeEvent[] }` |
| `GET` | `/api/products/{id}/history` | `PriceHistoryPoint[]` |
| `GET` | `/api/competitors` | `CompetitorSummary[]` |
| `GET` | `/api/health` | `HealthData` |

The exact TypeScript contracts live in `lib/types.ts`. Keep identifiers as strings, use ISO 8601 timestamps, and return money as numeric major currency units (for example, `749` means 749 DKK). The UI derives display formatting but expects calculated product comparison fields from the products endpoint. If the FastAPI service returns raw products and offers instead, perform `buildProductComparison()` in the API adapter before returning data to components.

## Mock mode

Mock mode is used when `NEXT_PUBLIC_API_BASE_URL` is missing or `NEXT_PUBLIC_USE_MOCK_API` is not explicitly set to `false`. Demo records live only in `lib/mock/data.ts` and include 24 products, four competitors, multiple price events, stock changes, stale checks, failed checks, and 21 days of price history.

To test an API failure state locally, disable mock mode and point the base URL at an unavailable server. Route-level error handling will show a recoverable customer-facing message.
