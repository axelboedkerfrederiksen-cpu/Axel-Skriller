# Pricegrid dashboard

A customer-facing competitor price-monitoring dashboard built with Next.js-compatible Vinext, React, TypeScript, Tailwind CSS, and Recharts. It consumes Price Monitor's customer-scoped read API and keeps the API credential on the server. Scraping and persistence remain in the separate backend.

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
2. Set `PRICE_MONITOR_API_BASE_URL` to the FastAPI origin without a trailing slash.
3. Set `PRICE_MONITOR_CUSTOMER_ID` to the customer UUID created in Price Monitor.
4. If the backend has API protection enabled, set `PRICE_MONITOR_API_TOKEN` to the same token.
5. Set `PRICEGRID_USE_MOCK_API=false` and restart the dashboard.

Example:

```env
PRICEGRID_USE_MOCK_API=false
PRICE_MONITOR_API_BASE_URL=https://pricing-api.example.com
PRICE_MONITOR_CUSTOMER_ID=0f83ee3c-609b-4ada-84c6-4b19a33676f3
PRICE_MONITOR_API_TOKEN=replace-with-the-backend-token
```

These are server-only variables—none should be prefixed with `NEXT_PUBLIC_`. All requests are centralized in `lib/api/client.ts`, use the bearer token only on the server, and opt out of caching so monitoring updates appear immediately. Browser CORS is not needed because the browser does not call FastAPI directly.

## Expected backend endpoints

| Method | Endpoint                                                        | Expected response     |
| ------ | --------------------------------------------------------------- | --------------------- |
| `GET`  | `/api/v1/customers/{customerId}/dashboard`                      | `DashboardData`       |
| `GET`  | `/api/v1/customers/{customerId}/dashboard/products`             | `ProductComparison[]` |
| `GET`  | `/api/v1/customers/{customerId}/dashboard/products/{productId}` | `ProductDetailData`   |
| `GET`  | `/api/v1/customers/{customerId}/dashboard/competitors`          | `CompetitorSummary[]` |
| `GET`  | `/api/v1/customers/{customerId}/dashboard/health`               | `HealthData`          |

The FastAPI backend now returns these exact camel-cased contracts. Identifiers are strings, timestamps use ISO 8601, nullable observations stay explicit, and money is represented as numeric major currency units (for example, `749` means 749 DKK).

## Mock mode

Mock mode is used unless `PRICEGRID_USE_MOCK_API=false` and both the API origin and customer ID are configured. Demo records live only in `lib/mock/data.ts` and include 24 products, four competitors, multiple price events, stock changes, stale checks, failed checks, and 21 days of price history. The navigation clearly labels whether the current deployment is showing demo or live data.

To test an API failure state locally, disable mock mode and point the base URL at an unavailable server. Route-level error handling will show a recoverable customer-facing message.
