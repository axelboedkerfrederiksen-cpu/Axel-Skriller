# Bill tracker

A simple React and TypeScript app for business bills. Built with the Sites React starter (Vinext/Vite), with a React reducer as the in-memory store. No database, login, API, or browser storage is used.

## Run locally

Requires Node.js 22.13 or newer and pnpm. Dependencies are already installed in this workspace.

```sh
pnpm dev --host 127.0.0.1
```

Open the local address printed in the terminal. Keep that terminal running; press Ctrl+C to stop it. On this Mac you can also double-click `Start bill tracker.command` in this folder, which locates the bundled runtime automatically.

For a fresh copy, run `pnpm install` first.

## Use

1. Enter the payee or description, amount in USD, due date, and payment status.
2. Select **Add bill**. The list sorts automatically by due date, earliest first.
3. Use **Mark paid** or **Mark unpaid** on a bill to update its status and both totals immediately.

Amounts must be positive, with at most two decimal places, up to $9,999,999.99. Past due dates are allowed. Each browser page has its own empty initial store. Refreshing or closing the page clears all bills.

## Project structure

- `app/page.tsx` — form, summaries, bill list, and state wiring.
- `app/globals.css` — responsive styling, including mobile bill cards.
- `app/layout.tsx` — page title and metadata.
- `lib/bills.ts` — data types, validation, exact money calculations, sorting, and reducer.
- `components/ui/` — accessible primitives included in the starter.
- `tests/bills.test.mjs` — amount, date, sorting, validation, and store behavior checks.

## Checks

```sh
pnpm test
pnpm typecheck
pnpm build
```

No site has been published. The app runs locally and uses USD consistently; currency can be changed in `lib/bills.ts` along with the form's currency symbol and validation copy.
