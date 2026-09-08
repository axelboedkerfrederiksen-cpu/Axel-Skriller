from __future__ import annotations

import json
from secrets import token_urlsafe

from fastapi.openapi.docs import get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse

SWAGGER_OAUTH2_REDIRECT_URL = "/docs/oauth2-redirect"

_SWAGGER_VERSION = "5.32.15"
_SWAGGER_CSS_URL = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{_SWAGGER_VERSION}/swagger-ui.css"
_SWAGGER_JS_URL = (
    f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{_SWAGGER_VERSION}/swagger-ui-bundle.js"
)
_SWAGGER_CSS_INTEGRITY = "sha384-fgyWYkUAamzuI8mJFu/xpRP0JWCJRwkwUwsYDoOYVHUJ8NQE5cENn8ib3ppwFFSX"
_SWAGGER_JS_INTEGRITY = "sha384-m7zaGj7MPzU+G4lz2eyy73GxK9bbRDr9bB2CSdj8wodg2wu/Wnt6wsoLP3JD+RS9"
_FAVICON_URL = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' "
    "fill='%23146b5d'/%3E%3Ctext x='16' y='20' text-anchor='middle' "
    "font-family='Arial' font-size='10' font-weight='700' fill='white'%3E"
    "PM%3C/text%3E%3C/svg%3E"
)

_DOCS_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>API workspace · Price Monitor</title>
    <link
      rel="stylesheet"
      href="__SWAGGER_CSS_URL__"
      integrity="__SWAGGER_CSS_INTEGRITY__"
      crossorigin="anonymous"
    >
    <link
      rel="icon"
      href="__FAVICON_URL__"
    >
    <style>
      :root {
        --pm-canvas: #f5f4ef;
        --pm-surface: #ffffff;
        --pm-surface-soft: #fafaf7;
        --pm-ink: #17201a;
        --pm-muted: #687169;
        --pm-line: #dadfd8;
        --pm-line-strong: #cbd2ca;
        --pm-accent: #146b5d;
        --pm-accent-soft: #e9f2ef;
        --pm-success: #2d6b4f;
        --pm-success-soft: #eaf4ed;
        --pm-danger: #98463d;
        color: var(--pm-ink);
        background: var(--pm-canvas);
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        font-synthesis: none;
      }
      * { box-sizing: border-box; }
      html { scroll-behavior: smooth; }
      body.pm-docs-page {
        min-width: 320px;
        min-height: 100vh;
        margin: 0;
        color: var(--pm-ink);
        background: var(--pm-canvas);
        font-size: 14px;
        line-height: 1.5;
      }
      .pm-docs-shell {
        width: min(1180px, calc(100% - 40px));
        margin: 0 auto;
      }
      .pm-docs-header {
        position: sticky;
        z-index: 100;
        top: 0;
        border-bottom: 1px solid var(--pm-line);
        background: var(--pm-surface);
      }
      .pm-docs-header-inner {
        display: flex;
        min-height: 62px;
        align-items: center;
        gap: 12px;
      }
      .pm-docs-brand {
        display: inline-flex;
        flex: 0 0 auto;
        align-items: center;
        gap: 9px;
        color: var(--pm-ink);
        font-weight: 720;
        letter-spacing: -.02em;
        text-decoration: none;
      }
      .pm-docs-mark {
        display: grid;
        width: 30px;
        height: 30px;
        place-items: center;
        border-radius: 6px;
        color: #ffffff;
        background: var(--pm-accent);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: -.04em;
      }
      .pm-docs-context,
      .pm-docs-service {
        display: inline-flex;
        min-height: 28px;
        align-items: center;
        gap: 7px;
        padding: 3px 9px;
        border: 1px solid var(--pm-line);
        border-radius: 4px;
        color: var(--pm-muted);
        background: var(--pm-surface-soft);
        font-size: 11px;
        font-weight: 700;
        text-decoration: none;
        white-space: nowrap;
      }
      .pm-docs-actions {
        display: flex;
        margin-left: auto;
        align-items: center;
        gap: 8px;
      }
      .pm-docs-back {
        display: inline-flex;
        min-height: 38px;
        align-items: center;
        justify-content: center;
        padding: 7px 11px;
        border: 1px solid var(--pm-line-strong);
        border-radius: 7px;
        color: var(--pm-ink);
        background: var(--pm-surface);
        font-size: 12px;
        font-weight: 720;
        text-decoration: none;
        white-space: nowrap;
      }
      .pm-docs-back:hover {
        border-color: #adb7ae;
        background: var(--pm-surface-soft);
      }
      .pm-docs-service {
        min-height: 30px;
        border-color: #bdd7c6;
        color: var(--pm-success);
        background: var(--pm-success-soft);
      }
      .pm-docs-dot {
        width: 6px;
        height: 6px;
        border-radius: 1px;
        background: var(--pm-success);
      }
      .pm-docs-main {
        min-height: calc(100vh - 115px);
        padding: 3px 0 36px;
      }
      .pm-docs-noscript {
        margin: 20px 0;
        padding: 12px 14px;
        border: 1px solid #e6c6c1;
        border-radius: 7px;
        color: var(--pm-danger);
        background: #f8ecea;
      }
      .pm-docs-footer {
        border-top: 1px solid var(--pm-line);
        color: var(--pm-muted);
        background: var(--pm-surface);
        font-size: 11px;
      }
      .pm-docs-footer-inner {
        display: flex;
        min-height: 52px;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
      }
      .pm-docs-footer a {
        color: var(--pm-ink);
        text-decoration: none;
      }
      .pm-docs-page a:focus-visible,
      .pm-docs-page button:focus-visible,
      .pm-docs-page input:focus-visible,
      .pm-docs-page select:focus-visible,
      .pm-docs-page textarea:focus-visible {
        outline: 2px solid var(--pm-accent) !important;
        outline-offset: 2px;
      }

      .swagger-ui {
        color: var(--pm-ink);
        font-family: inherit;
      }
      .swagger-ui .topbar { display: none; }
      .swagger-ui .wrapper {
        max-width: none;
        padding: 0;
      }
      .swagger-ui .information-container { margin: 0; }
      .swagger-ui .info { margin: 24px 0 17px; }
      .swagger-ui .info .title {
        margin: 0 0 7px;
        color: var(--pm-ink);
        font-family: inherit;
        font-size: clamp(26px, 4vw, 34px);
        font-weight: 760;
        line-height: 1.1;
        letter-spacing: -.035em;
      }
      .swagger-ui .info .title small {
        top: -2px;
        margin: 0 0 0 7px;
        padding: 3px 8px;
        border-radius: 3px;
        background: var(--pm-accent-soft);
        vertical-align: middle;
      }
      .swagger-ui .info .title small pre {
        color: var(--pm-accent);
        font-family: inherit;
        font-size: 10px;
        font-weight: 800;
      }
      .swagger-ui .info .title small.version-stamp {
        background: var(--pm-surface-soft);
      }
      .swagger-ui .info .title small.version-stamp pre { color: var(--pm-muted); }
      .swagger-ui .info p,
      .swagger-ui .info li,
      .swagger-ui .info table {
        max-width: 760px;
        margin: 5px 0;
        color: var(--pm-muted);
        font-family: inherit;
        font-size: 13px;
        line-height: 1.5;
      }
      .swagger-ui .info a {
        color: var(--pm-accent);
        font-family: inherit;
        font-weight: 700;
      }
      .swagger-ui .scheme-container {
        margin: 0 0 16px;
        padding: 12px 14px;
        border: 1px solid var(--pm-line);
        border-radius: 9px;
        background: var(--pm-surface);
        box-shadow: 0 1px 2px rgba(23, 32, 26, .035);
      }
      .swagger-ui .scheme-container .schemes {
        align-items: center;
        gap: 10px;
      }
      .swagger-ui .servers-title,
      .swagger-ui .schemes-title {
        color: var(--pm-muted);
        font-family: inherit;
        font-size: 12px;
      }
      .swagger-ui .btn,
      .swagger-ui button { font-family: inherit; }
      .swagger-ui .btn {
        min-height: 38px;
        padding: 7px 11px;
        border: 1px solid var(--pm-line-strong);
        border-radius: 7px;
        color: var(--pm-ink);
        background: var(--pm-surface);
        box-shadow: none;
        font-size: 12px;
        font-weight: 720;
      }
      .swagger-ui .btn:hover { box-shadow: none; }
      .swagger-ui .btn.authorize,
      .swagger-ui .btn.execute {
        border-color: var(--pm-accent);
        color: var(--pm-accent);
      }
      .swagger-ui .btn.execute {
        color: #ffffff;
        background: var(--pm-accent);
      }
      .swagger-ui .btn.authorize svg { fill: var(--pm-accent); }
      .swagger-ui .btn.cancel { color: var(--pm-danger); }
      .swagger-ui .filter-container {
        margin: 0 0 12px;
        padding: 0;
      }
      .swagger-ui .filter-container .operation-filter-input {
        width: min(100%, 360px);
        margin: 0;
      }
      .swagger-ui input[type=email],
      .swagger-ui input[type=file],
      .swagger-ui input[type=password],
      .swagger-ui input[type=search],
      .swagger-ui input[type=text],
      .swagger-ui textarea,
      .swagger-ui select {
        min-height: 40px;
        padding: 8px 10px;
        border: 1px solid var(--pm-line-strong);
        border-radius: 7px;
        color: var(--pm-ink);
        background: var(--pm-surface);
        font-family: inherit;
        font-size: 13px;
      }
      .swagger-ui .opblock-tag-section { scroll-margin-top: 76px; }
      .swagger-ui .opblock-tag {
        min-height: 50px;
        margin: 12px 0 8px;
        padding: 11px 14px;
        border: 1px solid var(--pm-line);
        border-bottom: 1px solid var(--pm-line);
        border-radius: 9px;
        color: var(--pm-ink);
        background: var(--pm-surface);
        font-family: inherit;
        font-size: 15px;
        font-weight: 740;
      }
      .swagger-ui .opblock-tag:hover { background: var(--pm-surface-soft); }
      .swagger-ui .opblock-tag small {
        color: var(--pm-muted);
        font-family: inherit;
        font-size: 11px;
      }
      .swagger-ui .opblock {
        margin: 0 0 8px;
        border: 1px solid var(--pm-line) !important;
        border-left: 3px solid var(--pm-accent) !important;
        border-radius: 7px;
        background: var(--pm-surface) !important;
        box-shadow: none;
      }
      .swagger-ui .opblock .opblock-summary {
        min-height: 48px;
        padding: 7px 10px;
        border-color: var(--pm-line) !important;
      }
      .swagger-ui .opblock .opblock-summary-method {
        min-width: 64px;
        min-height: 25px;
        padding: 4px 8px;
        border: 1px solid #bad3cd;
        border-radius: 3px;
        color: var(--pm-accent) !important;
        background: var(--pm-accent-soft) !important;
        font-family: inherit;
        font-size: 10px;
        font-weight: 800;
        line-height: 1.5;
        text-shadow: none;
      }
      .swagger-ui .opblock .opblock-summary-path,
      .swagger-ui .opblock .opblock-summary-path__deprecated {
        color: var(--pm-ink);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 13px;
        font-weight: 720;
      }
      .swagger-ui .opblock .opblock-summary-description {
        color: var(--pm-muted);
        font-family: inherit;
        font-size: 12px;
      }
      .swagger-ui .opblock .opblock-section-header {
        min-height: 46px;
        padding: 9px 13px;
        border-top: 1px solid var(--pm-line);
        background: var(--pm-surface-soft);
        box-shadow: none;
      }
      .swagger-ui .opblock .opblock-section-header h4,
      .swagger-ui .opblock .opblock-section-header label {
        color: var(--pm-ink);
        font-family: inherit;
        font-size: 12px;
      }
      .swagger-ui .opblock-body,
      .swagger-ui .responses-inner,
      .swagger-ui .opblock-description-wrapper,
      .swagger-ui .opblock-external-docs-wrapper,
      .swagger-ui .opblock-title_normal {
        color: var(--pm-ink);
        font-family: inherit;
        font-size: 12px;
      }
      .swagger-ui table thead tr td,
      .swagger-ui table thead tr th {
        padding: 9px 8px;
        border-bottom: 1px solid var(--pm-line);
        color: var(--pm-muted);
        font-family: inherit;
        font-size: 10px;
        letter-spacing: .04em;
        text-transform: uppercase;
      }
      .swagger-ui .parameter__name,
      .swagger-ui .response-col_status {
        color: var(--pm-ink);
        font-family: inherit;
        font-size: 12px;
      }
      .swagger-ui .parameter__type,
      .swagger-ui .parameter__in,
      .swagger-ui .response-col_description {
        color: var(--pm-muted);
        font-family: inherit;
        font-size: 11px;
      }
      .swagger-ui .model-box,
      .swagger-ui section.models {
        border-color: var(--pm-line);
        border-radius: 7px;
        background: var(--pm-surface);
      }
      .swagger-ui section.models h4,
      .swagger-ui section.models h5,
      .swagger-ui .model-title,
      .swagger-ui .model {
        color: var(--pm-ink);
        font-family: inherit;
      }
      .swagger-ui .highlight-code > .microlight,
      .swagger-ui .microlight {
        border-radius: 6px;
        background: #1e2721 !important;
        font-size: 11px;
      }
      .swagger-ui .dialog-ux .modal-ux {
        border: 1px solid var(--pm-line);
        border-radius: 9px;
        background: var(--pm-surface);
        box-shadow: 0 18px 55px rgba(23, 32, 26, .16);
      }
      .swagger-ui .dialog-ux .modal-ux-header {
        border-bottom: 1px solid var(--pm-line);
      }
      .swagger-ui .dialog-ux .modal-ux-header h3,
      .swagger-ui .dialog-ux .modal-ux-content h4,
      .swagger-ui .dialog-ux .modal-ux-content p,
      .swagger-ui .dialog-ux .modal-ux-content label {
        color: var(--pm-ink);
        font-family: inherit;
      }
      .swagger-ui .loading-container .loading:after { color: var(--pm-accent); }

      @media (max-width: 620px) {
        .pm-docs-shell { width: min(calc(100% - 24px), 1180px); }
        .pm-docs-header-inner {
          flex-wrap: wrap;
          gap: 8px 14px;
          padding: 10px 0;
        }
        .pm-docs-context { display: none; }
        .pm-docs-actions {
          order: 3;
          width: 100%;
          margin-left: 0;
          justify-content: space-between;
        }
        .pm-docs-back,
        .pm-docs-service { min-height: 44px; }
        .swagger-ui .info { margin-top: 20px; }
        .swagger-ui .scheme-container { padding: 11px; }
        .swagger-ui .scheme-container .schemes {
          align-items: stretch;
          flex-direction: column;
        }
        .swagger-ui .auth-wrapper { justify-content: stretch; }
        .swagger-ui .auth-wrapper .authorize {
          width: 100%;
          justify-content: center;
        }
        .swagger-ui .opblock .opblock-summary {
          flex-wrap: wrap;
          gap: 5px;
        }
        .swagger-ui .opblock .opblock-summary-path {
          min-width: 0;
          overflow-wrap: anywhere;
          word-break: break-word;
        }
        .swagger-ui .opblock .opblock-summary-description {
          width: 100%;
          padding-left: 72px;
        }
        .swagger-ui .parameters-col_description,
        .swagger-ui .response-col_description { min-width: 180px; }
        .pm-docs-footer-inner {
          align-items: flex-start;
          flex-direction: column;
          justify-content: center;
          gap: 3px;
          padding: 12px 0;
        }
      }
      @media (prefers-reduced-motion: reduce) {
        html { scroll-behavior: auto; }
      }
    </style>
  </head>
  <body class="pm-docs-page" data-ui="price-monitor-api-workspace">
    <header class="pm-docs-header">
      <div class="pm-docs-shell pm-docs-header-inner">
        <a class="pm-docs-brand" href="/" aria-label="Price Monitor homepage">
          <span class="pm-docs-mark" aria-hidden="true">PM</span>
          <span>Price Monitor</span>
        </a>
        <span class="pm-docs-context">API workspace</span>
        <nav class="pm-docs-actions" aria-label="API workspace navigation">
          <a class="pm-docs-back" href="/">
            <span aria-hidden="true">←</span>&nbsp; Back to homepage
          </a>
          <a
            class="pm-docs-service"
            href="/healthz"
            aria-label="Price Monitor service status: online"
          >
            <span class="pm-docs-dot" aria-hidden="true"></span>
            Service online
          </a>
        </nav>
      </div>
    </header>
    <main class="pm-docs-shell pm-docs-main">
      <noscript>
        <p class="pm-docs-noscript">JavaScript is required to use the API workspace.</p>
      </noscript>
      <div id="swagger-ui"></div>
    </main>
    <footer class="pm-docs-footer">
      <div class="pm-docs-shell pm-docs-footer-inner">
        <span>Price Monitor beta · API version 0.1.0</span>
        <a href="/">Return to operations overview</a>
      </div>
    </footer>
    <script
      src="__SWAGGER_JS_URL__"
      integrity="__SWAGGER_JS_INTEGRITY__"
      crossorigin="anonymous"
    ></script>
    <script nonce="__SCRIPT_NONCE__">
      window.ui = SwaggerUIBundle({
        url: __OPENAPI_URL__,
__SWAGGER_PARAMETERS__,
        oauth2RedirectUrl: window.location.origin + __OAUTH2_REDIRECT_URL__,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset,
        ],
      });
    </script>
  </body>
</html>
"""


def _json_for_html(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _security_headers(script_nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'none'; "
            "style-src 'unsafe-inline' https://cdn.jsdelivr.net; "
            f"script-src 'nonce-{script_nonce}' https://cdn.jsdelivr.net; "
            "connect-src 'self'; img-src 'self' data:; "
            "font-src 'self' data: https://cdn.jsdelivr.net; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'"
        ),
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


def api_docs_response(*, openapi_url: str) -> HTMLResponse:
    """Render the interactive API workspace inside the Price Monitor visual shell."""

    script_nonce = token_urlsafe(24)
    parameters: dict[str, object] = {
        "dom_id": "#swagger-ui",
        "layout": "BaseLayout",
        "deepLinking": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "displayRequestDuration": True,
        "docExpansion": "list",
        "filter": True,
        "persistAuthorization": False,
    }
    serialized_parameters = ",\n".join(
        f"        {_json_for_html(key)}: {_json_for_html(value)}"
        for key, value in parameters.items()
    )
    content = (
        _DOCS_TEMPLATE.replace("__SWAGGER_CSS_URL__", _SWAGGER_CSS_URL)
        .replace("__SWAGGER_CSS_INTEGRITY__", _SWAGGER_CSS_INTEGRITY)
        .replace("__SWAGGER_JS_URL__", _SWAGGER_JS_URL)
        .replace("__SWAGGER_JS_INTEGRITY__", _SWAGGER_JS_INTEGRITY)
        .replace("__FAVICON_URL__", _FAVICON_URL)
        .replace("__SCRIPT_NONCE__", script_nonce)
        .replace("__OPENAPI_URL__", _json_for_html(openapi_url))
        .replace("__SWAGGER_PARAMETERS__", serialized_parameters)
        .replace("__OAUTH2_REDIRECT_URL__", _json_for_html(SWAGGER_OAUTH2_REDIRECT_URL))
    )
    return HTMLResponse(content=content, headers=_security_headers(script_nonce))


def oauth2_redirect_response() -> HTMLResponse:
    """Keep Swagger UI's standard OAuth redirect endpoint available."""

    return get_swagger_ui_oauth2_redirect_html()


__all__ = ["SWAGGER_OAUTH2_REDIRECT_URL", "api_docs_response", "oauth2_redirect_response"]
