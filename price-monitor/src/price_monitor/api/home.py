from __future__ import annotations

from fastapi.responses import HTMLResponse

_HOME_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>Price Monitor · Service online</title>
    <style>
      :root {
        color: #152238;
        background: #f4f7fb;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
      }
      * { box-sizing: border-box; }
      body {
        min-height: 100vh;
        margin: 0;
        background:
          radial-gradient(circle at 10% 5%, rgba(96, 165, 250, .22), transparent 34rem),
          radial-gradient(circle at 90% 90%, rgba(52, 211, 153, .18), transparent 30rem),
          #f4f7fb;
      }
      a { color: inherit; }
      .shell {
        width: min(1100px, calc(100% - 2rem));
        margin: 0 auto;
        padding: 1.25rem 0 2.5rem;
      }
      header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
      }
      .brand {
        display: flex;
        align-items: center;
        gap: .7rem;
        font-weight: 800;
        letter-spacing: -.02em;
      }
      .mark {
        display: grid;
        width: 2.5rem;
        height: 2.5rem;
        place-items: center;
        border-radius: .8rem;
        color: white;
        background: linear-gradient(135deg, #2563eb, #14b8a6);
        box-shadow: 0 10px 25px rgba(37, 99, 235, .24);
      }
      .status {
        display: inline-flex;
        align-items: center;
        gap: .5rem;
        padding: .5rem .8rem;
        border: 1px solid #bbf7d0;
        border-radius: 999px;
        color: #166534;
        background: rgba(240, 253, 244, .9);
        font-size: .85rem;
        font-weight: 700;
      }
      .dot {
        width: .55rem;
        height: .55rem;
        border-radius: 50%;
        background: #22c55e;
        box-shadow: 0 0 0 .25rem rgba(34, 197, 94, .13);
      }
      main {
        padding-top: clamp(4rem, 10vw, 8rem);
      }
      .eyebrow {
        margin: 0 0 1rem;
        color: #2563eb;
        font-size: .8rem;
        font-weight: 800;
        letter-spacing: .14em;
        text-transform: uppercase;
      }
      h1 {
        max-width: 780px;
        margin: 0;
        color: #0f172a;
        font-size: clamp(2.7rem, 8vw, 5.6rem);
        line-height: .98;
        letter-spacing: -.065em;
      }
      .lead {
        max-width: 650px;
        margin: 1.5rem 0 0;
        color: #526079;
        font-size: clamp(1rem, 2.2vw, 1.25rem);
        line-height: 1.7;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: .75rem;
        margin-top: 2rem;
      }
      .button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 3rem;
        padding: .75rem 1.1rem;
        border: 1px solid #cbd5e1;
        border-radius: .85rem;
        text-decoration: none;
        background: rgba(255, 255, 255, .78);
        font-weight: 750;
        transition: transform .16s ease, box-shadow .16s ease;
      }
      .button:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 28px rgba(15, 23, 42, .1);
      }
      .button.primary {
        border-color: #1d4ed8;
        color: white;
        background: #2563eb;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 1rem;
        margin-top: clamp(3.5rem, 8vw, 6rem);
      }
      .card {
        padding: 1.35rem;
        border: 1px solid rgba(203, 213, 225, .9);
        border-radius: 1.15rem;
        background: rgba(255, 255, 255, .72);
        box-shadow: 0 18px 55px rgba(15, 23, 42, .06);
        backdrop-filter: blur(12px);
      }
      .card b {
        display: block;
        margin-bottom: .45rem;
        color: #0f172a;
        font-size: 1rem;
      }
      .card p {
        margin: 0;
        color: #64748b;
        font-size: .92rem;
        line-height: 1.55;
      }
      .note {
        margin-top: 1rem;
        padding: 1rem 1.2rem;
        border: 1px solid #dbeafe;
        border-radius: 1rem;
        color: #475569;
        background: rgba(239, 246, 255, .72);
        font-size: .86rem;
        line-height: 1.55;
      }
      footer {
        margin-top: 2.5rem;
        color: #94a3b8;
        font-size: .78rem;
      }
      @media (max-width: 720px) {
        .grid { grid-template-columns: 1fr; }
        main { padding-top: 4rem; }
        h1 { letter-spacing: -.05em; }
      }
      @media (prefers-reduced-motion: reduce) {
        .button { transition: none; }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <header>
        <div class="brand"><span class="mark" aria-hidden="true">PM</span>Price Monitor</div>
        <div class="status"><span class="dot" aria-hidden="true"></span>Service is online</div>
      </header>
      <main>
        <p class="eyebrow">Competitor intelligence</p>
        <h1>Price monitoring you can trust.</h1>
        <p class="lead">
          Track competitor offers, keep an auditable price history, and detect scraper
          problems before unreliable data reaches your decisions.
        </p>
        <div class="actions">
          <a class="button primary" href="/docs">Open API workspace</a>
          <a class="button" href="/healthz">Check service status</a>
        </div>
        <section class="grid" aria-label="Price Monitor capabilities">
          <article class="card">
            <b>Validated observations</b>
            <p>Price, currency, identity, and extraction evidence are checked before saving.</p>
          </article>
          <article class="card">
            <b>Historical changes</b>
            <p>Accepted observations form a clear timeline of increases and decreases.</p>
          </article>
          <article class="card">
            <b>Guarded recovery</b>
            <p>
              Broken selectors can be diagnosed and tested without silently changing live logic.
            </p>
          </article>
        </section>
        <p class="note">
          This beta preview uses temporary storage. Continuous monitoring requires the durable
          database and worker setup described in the project guide.
        </p>
      </main>
      <footer>Price Monitor beta · API version 0.1.0</footer>
    </div>
  </body>
</html>
"""

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def homepage_response() -> HTMLResponse:
    """Return a static landing page without touching the database or exposing settings."""

    return HTMLResponse(content=_HOME_HTML, headers=_SECURITY_HEADERS)


__all__ = ["homepage_response"]
