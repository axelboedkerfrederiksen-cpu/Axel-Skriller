(() => {
  "use strict";

  const API_ROOT = "/api/v1";
  const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const main = document.querySelector("#main-content");
  const workspaceSelect = document.querySelector("#workspace-select");
  const serviceStatus = document.querySelector("#service-status");
  const sessionLogout = document.querySelector("#session-logout");
  const toastRegion = document.querySelector("#toast-region");

  const state = {
    controller: null,
    customers: [],
    customer: null,
    partialErrors: [],
    route: null,
    productFilter: "all",
    competitorFilter: "all",
    search: "",
    data: null,
    session: null,
  };

  class ApiError extends Error {
    constructor(status, kind = "request") {
      super(`Price Monitor ${kind} request failed`);
      this.name = "ApiError";
      this.status = status;
      this.kind = kind;
    }
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
    );
  }

  function safeId(value) {
    return UUID_PATTERN.test(String(value)) ? String(value) : "";
  }

  function safeExternalUrl(value) {
    try {
      const url = new URL(String(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function formatHost(value) {
    try {
      return new URL(String(value)).hostname;
    } catch (_error) {
      return "Address unavailable";
    }
  }

  function selectedCustomerId() {
    return safeId(state.customer?.id);
  }

  function appHref(path, extras = {}) {
    const parameters = new URLSearchParams();
    const customerId = selectedCustomerId();
    if (customerId) parameters.set("customer", customerId);
    Object.entries(extras).forEach(([key, value]) => {
      if (value !== null && value !== undefined && String(value)) {
        parameters.set(key, String(value));
      }
    });
    const query = parameters.toString();
    return query ? `${path}?${query}` : path;
  }

  function productHref(productId) {
    const id = safeId(productId);
    return id ? appHref(`/products/${id}`) : appHref("/products");
  }

  function currentTimeZone() {
    const candidate = state.customer?.timezone;
    if (!candidate) return undefined;
    try {
      new Intl.DateTimeFormat(undefined, { timeZone: candidate }).format(new Date());
      return candidate;
    } catch (_error) {
      return undefined;
    }
  }

  function formatExactTime(value) {
    if (!value) return "Never";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Unavailable";
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short",
      timeZone: currentTimeZone(),
    }).format(date);
  }

  function formatRelativeTime(value) {
    if (!value) return "Never checked";
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) return "Time unavailable";
    const seconds = Math.round((timestamp - Date.now()) / 1000);
    const absolute = Math.abs(seconds);
    let divisor = 1;
    let unit = "second";
    if (absolute >= 86_400) {
      divisor = 86_400;
      unit = "day";
    } else if (absolute >= 3_600) {
      divisor = 3_600;
      unit = "hour";
    } else if (absolute >= 60) {
      divisor = 60;
      unit = "minute";
    }
    return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
      Math.round(seconds / divisor),
      unit,
    );
  }

  function timeMarkup(value, tone = "") {
    if (!value) {
      return '<span class="timestamp-stack"><span class="pill waiting">Never checked</span></span>';
    }
    const safe = escapeHtml(value);
    const toneClass = tone ? ` ${escapeHtml(tone)}` : "";
    return `<span class="timestamp-stack">
      <span class="pill${toneClass}">${escapeHtml(formatRelativeTime(value))}</span>
      <time datetime="${safe}">${escapeHtml(formatExactTime(value))}</time>
    </span>`;
  }

  function formatPrice(value, currency) {
    if (value === null || value === undefined || value === "") return "No price";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "Price unavailable";
    const code = String(currency || "").toUpperCase();
    if (/^[A-Z]{3}$/.test(code)) {
      try {
        return new Intl.NumberFormat(undefined, {
          style: "currency",
          currency: code,
          minimumFractionDigits: 2,
          maximumFractionDigits: 4,
        }).format(numeric);
      } catch (_error) {
        return `${code} ${numeric.toFixed(2)}`;
      }
    }
    return numeric.toFixed(2);
  }

  function formatChartPrice(value, currency) {
    const numeric = Number(value);
    const code = String(currency || "").toUpperCase();
    if (!Number.isFinite(numeric)) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        style: /^[A-Z]{3}$/.test(code) ? "currency" : "decimal",
        currency: /^[A-Z]{3}$/.test(code) ? code : undefined,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric);
    } catch (_error) {
      return numeric.toFixed(2);
    }
  }

  function formatPercent(value, includeSign = true) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "—";
    const absolute = Math.abs(numeric).toLocaleString(undefined, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    if (!includeSign) return `${absolute}%`;
    if (numeric < 0) return `−${absolute}%`;
    if (numeric > 0) return `+${absolute}%`;
    return "0.0%";
  }

  function formatInterval(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "Schedule unavailable";
    if (value % 86_400 === 0) {
      const days = value / 86_400;
      return `Every ${days} day${days === 1 ? "" : "s"}`;
    }
    if (value % 3_600 === 0) {
      const hours = value / 3_600;
      return `Every ${hours} hour${hours === 1 ? "" : "s"}`;
    }
    const minutes = Math.round(value / 60);
    return `Every ${minutes} min`;
  }

  function titleForRoute(route) {
    const titles = {
      overview: "Overview",
      products: "Products",
      "add-product": "Add product",
      "product-detail": "Product",
      competitors: "Competitors",
      alerts: "Alerts",
      missing: "Not found",
    };
    return titles[route.name] || "Price Monitor";
  }

  function parseRoute() {
    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    if (path === "/") return { name: "overview" };
    if (path === "/products") return { name: "products" };
    if (path === "/products/new") return { name: "add-product" };
    if (path === "/competitors") return { name: "competitors" };
    if (path === "/alerts") return { name: "alerts" };
    const detail = path.match(/^\/products\/([^/]+)$/);
    if (detail && safeId(detail[1])) {
      return { name: "product-detail", productId: detail[1] };
    }
    return { name: "missing" };
  }

  async function request(path, options = {}) {
    const method = options.method || "GET";
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (!["GET", "HEAD"].includes(method)) headers["X-Price-Monitor-UI"] = "1";
    let response;
    try {
      response = await fetch(`${API_ROOT}${path}`, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: "same-origin",
        cache: "no-store",
        signal: options.signal || state.controller?.signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new ApiError(0, options.kind);
    }
    if (!response.ok) throw new ApiError(response.status, options.kind);
    if (response.status === 204) return null;
    try {
      return await response.json();
    } catch (_error) {
      throw new ApiError(502, options.kind);
    }
  }

  async function optionalRequest(path, fallback, label, options = {}) {
    try {
      return await request(path, options);
    } catch (error) {
      if (error?.name === "AbortError" || error?.status === 401 || error?.status === 403) {
        throw error;
      }
      if (!(options.allow404 && error?.status === 404)) {
        state.partialErrors.push(label);
      }
      return fallback;
    }
  }

  function safeActionMessage(error, action) {
    if (error?.status === 401 || error?.status === 403) return "Operator access required.";
    if (error?.status === 409) return `${action} already exists.`;
    if (error?.status === 422) return `Check the ${action.toLowerCase()} details.`;
    if (error?.status === 404) return `${action} is no longer available.`;
    if (error?.status === 0) return "Could not reach Price Monitor.";
    return `${action} could not be saved.`;
  }

  function showToast(message, tone = "") {
    const toast = document.createElement("div");
    toast.className = `toast${tone ? ` ${tone}` : ""}`;
    toast.setAttribute("role", tone === "error" ? "alert" : "status");
    toast.textContent = message;
    toastRegion.replaceChildren(toast);
    window.setTimeout(() => {
      if (toast.isConnected) toast.remove();
    }, 5000);
  }

  function setFormBusy(form, busy, label = "Saving") {
    form.setAttribute("aria-busy", String(busy));
    form.querySelectorAll("button, input, select").forEach((control) => {
      control.disabled = busy || control.dataset.permanentDisabled === "true";
    });
    const submit = form.querySelector('[type="submit"]');
    if (submit) {
      if (busy) {
        submit.dataset.idleLabel = submit.textContent.trim();
        submit.textContent = label;
      } else if (submit.dataset.idleLabel) {
        submit.textContent = submit.dataset.idleLabel;
      }
    }
  }

  function partialNotice() {
    if (!state.partialErrors.length) return "";
    return `<div class="notice warning" role="status">
      <strong>Partial data.</strong> Some monitoring details are unavailable. Shown values are from available records.
    </div>`;
  }

  function loadingMarkup(label) {
    return `<div class="loading-state" role="status" aria-live="polite">
      <span class="eyebrow">${escapeHtml(state.customer?.name || "Workspace")}</span>
      <h1>${escapeHtml(label)}</h1>
      <div class="loading-lines" aria-hidden="true"><span></span><span></span><span></span></div>
    </div>`;
  }

  function pageHeading(eyebrow, title, lede, actions = "") {
    return `<section class="page-heading">
      <div class="page-heading-copy">
        <span class="eyebrow">${escapeHtml(eyebrow)}</span>
        <h1>${escapeHtml(title)}</h1>
        ${lede ? `<p class="lede">${escapeHtml(lede)}</p>` : ""}
      </div>
      ${actions ? `<div class="heading-actions">${actions}</div>` : ""}
    </section>`;
  }

  function emptyState(title, copy, actions = "") {
    return `<div class="empty-state">
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(copy)}</p>
      ${actions ? `<div class="button-row">${actions}</div>` : ""}
    </div>`;
  }

  function renderFatal(error) {
    const unauthorized = error?.status === 401 || error?.status === 403;
    document.title = `${unauthorized ? "Access required" : "Unavailable"} · Price Monitor`;
    main.innerHTML = `<div class="error-state" role="alert">
      <span class="eyebrow">${unauthorized ? "Protected workspace" : "Connection error"}</span>
      <h1>${unauthorized ? "Operator access required" : "Price data unavailable"}</h1>
      <p>${
        unauthorized
          ? "This browser does not receive or store the deployment token. Use an authenticated operator session."
          : "Price Monitor could not load this workspace. No saved data was changed."
      }</p>
      <div class="button-row">
        <button class="button primary" type="button" data-action="retry">Retry</button>
        ${unauthorized ? '<a class="button" href="/docs">API workspace</a>' : ""}
      </div>
    </div>`;
    main.removeAttribute("aria-busy");
  }

  function updateHeader(route) {
    document.querySelectorAll("[data-route]").forEach((link) => {
      const active =
        link.dataset.route === route.name ||
        (link.dataset.route === "products" && ["add-product", "product-detail"].includes(route.name));
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
      const path = link.dataset.route === "overview" ? "/" : `/${link.dataset.route}`;
      link.href = appHref(path);
    });
    const brand = document.querySelector(".brand");
    brand.href = appHref("/");

    workspaceSelect.replaceChildren();
    if (!state.customers.length) {
      workspaceSelect.append(new Option("No workspace", ""));
      workspaceSelect.disabled = true;
      return;
    }
    state.customers.forEach((customer) => {
      const suffix = customer.is_active ? "" : " (inactive)";
      workspaceSelect.append(new Option(`${customer.name}${suffix}`, customer.id));
    });
    workspaceSelect.value = state.customer?.id || "";
    workspaceSelect.disabled = false;
  }

  async function checkService() {
    try {
      const response = await fetch("/readyz", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("not ready");
      serviceStatus.className = "service-pill is-ready";
      serviceStatus.querySelector("span:last-child").textContent = "Ready";
      serviceStatus.setAttribute("aria-label", "Service ready");
    } catch (_error) {
      serviceStatus.className = "service-pill is-error";
      serviceStatus.querySelector("span:last-child").textContent = "Offline";
      serviceStatus.setAttribute("aria-label", "Service unavailable");
    }
  }

  async function loadCustomers() {
    const customers = await request("/customers", { kind: "workspace" });
    state.customers = Array.isArray(customers) ? customers : [];
    const requested = new URLSearchParams(window.location.search).get("customer");
    state.customer =
      state.customers.find((customer) => customer.id === requested) ||
      state.customers.find((customer) => customer.is_active) ||
      state.customers[0] ||
      null;
  }

  async function loadCoreData() {
    const customerId = selectedCustomerId();
    const [products, competitors] = await Promise.all([
      optionalRequest(`/customers/${customerId}/products`, [], "products"),
      optionalRequest(`/customers/${customerId}/competitors`, [], "competitors"),
    ]);
    return { products, competitors };
  }

  async function loadProductBundle(product, options = {}) {
    const productId = safeId(product.id);
    const [targets, offers, history] = await Promise.all([
      optionalRequest(`/products/${productId}/competitor-products`, [], "monitoring targets"),
      options.offers === false
        ? Promise.resolve([])
        : optionalRequest(`/products/${productId}/offers`, [], "offers"),
      options.history === false
        ? Promise.resolve([])
        : optionalRequest(`/products/${productId}/price-history?limit=200`, [], "price history"),
    ]);
    const latestResults = {};
    if (options.results !== false) {
      await Promise.all(
        targets.map(async (target) => {
          const id = safeId(target.id);
          const value = await optionalRequest(
            `/competitor-products/${id}/monitoring-status`,
            null,
            "check status",
            { allow404: true },
          );
          latestResults[target.id] = value;
        }),
      );
    }
    return { product, targets, offers, history, latestResults };
  }

  async function loadMonitoringData() {
    const core = await loadCoreData();
    const bundles = await Promise.all(core.products.map((product) => loadProductBundle(product)));
    const health = {};
    await Promise.all(
      core.competitors.map(async (competitor) => {
        health[competitor.id] = await optionalRequest(
          `/competitors/${safeId(competitor.id)}/health-summary`,
          null,
          "scraper health",
          { allow404: true },
        );
      }),
    );
    return { ...core, bundles, health };
  }

  function competitorMap(competitors) {
    return new Map(competitors.map((competitor) => [competitor.id, competitor]));
  }

  function targetStatus(target, competitor, latestResult) {
    if (!target.is_active || competitor?.is_active === false) {
      return { key: "paused", label: "Paused", tone: "" };
    }
    if (latestResult?.latest_job_status === "queued") {
      const queuedAt = latestResult.latest_job_queued_at;
      const queuedAge = queuedAt ? (Date.now() - new Date(queuedAt).getTime()) / 1000 : 0;
      if (Number.isFinite(queuedAge) && queuedAge > 300) {
        return {
          key: "stale",
          label: "Queue stalled",
          tone: "stale",
          stalled: "queued",
          eventTime: queuedAt,
        };
      }
      return { key: "checking", label: "Queued", tone: "checking" };
    }
    if (latestResult?.latest_job_status === "running") {
      const startedAt = latestResult.latest_job_started_at;
      const attemptSeconds =
        Number(competitor?.timeout_seconds || 15) * (Number(competitor?.max_retries || 2) + 1);
      const stalledAfter = Math.max(300, attemptSeconds * 2);
      const runningAge = startedAt ? (Date.now() - new Date(startedAt).getTime()) / 1000 : 0;
      if (Number.isFinite(runningAge) && runningAge > stalledAfter) {
        return {
          key: "stale",
          label: "Check stalled",
          tone: "stale",
          stalled: "running",
          eventTime: startedAt,
        };
      }
      return { key: "checking", label: "Checking", tone: "checking" };
    }
    if (Number(target.consecutive_failures) > 0) {
      return { key: "failed", label: "Check failed", tone: "failed" };
    }
    const lastSuccess = target.last_success_at || target.current_observed_at;
    if (!lastSuccess) return { key: "waiting", label: "Not checked", tone: "waiting" };
    const interval = Number(target.schedule_interval_seconds || competitor?.schedule_interval_seconds || 3600);
    const ageSeconds = (Date.now() - new Date(lastSuccess).getTime()) / 1000;
    if (Number.isFinite(ageSeconds) && ageSeconds > interval * 2) {
      return { key: "stale", label: "Stale", tone: "stale" };
    }
    return { key: "fresh", label: "Fresh", tone: "fresh" };
  }

  function productStatus(bundle, competitorsById) {
    if (!bundle.product.is_active) return { key: "paused", label: "Paused", tone: "" };
    if (!bundle.targets.length) return { key: "waiting", label: "No offers", tone: "waiting" };
    const values = bundle.targets.map((target) =>
      targetStatus(target, competitorsById.get(target.competitor_id), bundle.latestResults[target.id]),
    );
    const priority = ["failed", "stale", "checking", "waiting", "paused", "fresh"];
    return values.sort((left, right) => priority.indexOf(left.key) - priority.indexOf(right.key))[0];
  }

  function statusPill(status) {
    return `<span class="pill ${escapeHtml(status.tone)}">${escapeHtml(status.label)}</span>`;
  }

  function latestTrustedTime(bundle) {
    const times = bundle.targets
      .map((target) => target.current_observed_at || target.last_success_at)
      .filter(Boolean)
      .sort();
    return times.at(-1) || null;
  }

  function latestChange(bundle) {
    return bundle.history[0] || null;
  }

  function changeMarkup(change) {
    if (!change) return '<span class="pill">No change yet</span>';
    if (change.change_kind === "increase") {
      return `<span class="pill increase">${escapeHtml(formatPercent(change.change_percent))}</span>`;
    }
    if (change.change_kind === "decrease") {
      return `<span class="pill decrease">${escapeHtml(formatPercent(change.change_percent))}</span>`;
    }
    if (change.change_kind === "currency_changed") {
      return '<span class="pill warning">Currency changed</span>';
    }
    if (change.change_kind === "initial") return '<span class="pill">Initial price</span>';
    return '<span class="pill">Unchanged</span>';
  }

  function bestOffer(bundle) {
    const priced = bundle.offers.filter((offer) => Number.isFinite(Number(offer.price)) && offer.currency);
    if (!priced.length) return null;
    const preferredCurrency = bundle.product.currency;
    let comparable = preferredCurrency
      ? priced.filter((offer) => offer.currency === preferredCurrency)
      : priced;
    if (!comparable.length) {
      const fallbackCurrencies = new Set(priced.map((offer) => offer.currency));
      if (fallbackCurrencies.size > 1) return { mixed: true };
      comparable = priced;
    }
    if (!preferredCurrency && new Set(comparable.map((offer) => offer.currency)).size > 1) {
      return { mixed: true };
    }
    return comparable.sort((left, right) => Number(left.price) - Number(right.price))[0];
  }

  function productTableRows(data) {
    const competitorsById = competitorMap(data.competitors);
    return data.bundles.map((bundle) => {
      const status = productStatus(bundle, competitorsById);
      const best = bestOffer(bundle);
      const change = latestChange(bundle);
      const competitorIds = bundle.targets.map((target) => target.competitor_id).join(" ");
      const name = bundle.product.name || "Unnamed product";
      return `<tr data-href="${escapeHtml(productHref(bundle.product.id))}"
        data-product-state="${escapeHtml(status.key)}"
        data-search="${escapeHtml(`${name} ${bundle.product.sku || ""}`.toLowerCase())}"
        data-competitors="${escapeHtml(competitorIds)}">
        <td>
          <a class="cell-title" href="${escapeHtml(productHref(bundle.product.id))}" data-nav>${escapeHtml(name)}</a>
          <span class="cell-subtitle">${escapeHtml(bundle.product.sku || "No SKU")}</span>
        </td>
        <td><span class="price">${escapeHtml(formatPrice(bundle.product.current_own_price, bundle.product.currency))}</span></td>
        <td>${
          best?.mixed
            ? '<span class="pill warning">Mixed currencies</span>'
            : best
              ? `<span class="price">${escapeHtml(formatPrice(best.price, best.currency))}</span><span class="cell-subtitle">${escapeHtml(best.competitor_name)}</span>`
              : '<span class="muted">No trusted offer</span>'
        }</td>
        <td>${changeMarkup(change)}</td>
        <td>${statusPill(status)}</td>
        <td>${timeMarkup(latestTrustedTime(bundle), status.key === "stale" ? "stale" : "")}</td>
      </tr>`;
    }).join("");
  }

  function productTable(data, id = "product-table") {
    if (!data.bundles.length) {
      return emptyState(
        "No products",
        "Add a product and competitor URL to start monitoring.",
        `<a class="button primary" href="${escapeHtml(appHref("/products/new"))}" data-nav>Add product</a>`,
      );
    }
    return `<div class="table-wrap">
      <table id="${escapeHtml(id)}">
        <caption class="sr-only">Products and their latest trusted competitor prices</caption>
        <thead><tr>
          <th scope="col">Product</th>
          <th scope="col">Own price</th>
          <th scope="col">Best offer</th>
          <th scope="col">Change</th>
          <th scope="col">Status</th>
          <th scope="col">Last trusted</th>
        </tr></thead>
        <tbody>${productTableRows(data)}</tbody>
      </table>
    </div>`;
  }

  function attentionItems(data) {
    const competitorsById = competitorMap(data.competitors);
    const items = [];
    data.bundles.forEach((bundle) => {
      if (!bundle.targets.length && bundle.product.is_active) {
        items.push({
          product: bundle.product,
          competitor: null,
          status: { key: "waiting", label: "No offers", tone: "waiting" },
          copy: "No competitor URL connected.",
          eventTime: null,
        });
      }
      bundle.targets.forEach((target) => {
        const competitor = competitorsById.get(target.competitor_id);
        const status = targetStatus(target, competitor, bundle.latestResults[target.id]);
        if (!["failed", "stale", "waiting"].includes(status.key)) return;
        const eventTime =
          status.stalled
            ? status.eventTime
            : status.key === "failed"
            ? target.last_attempt_at
            : target.last_success_at || target.current_observed_at;
        let copy = "No trusted observation yet.";
        if (status.stalled === "queued") {
          copy = `Queued ${formatRelativeTime(eventTime)}.`;
        } else if (status.stalled === "running") {
          copy = `Started ${formatRelativeTime(eventTime)}.`;
        } else if (status.key === "failed" && target.current_price !== null) {
          copy = `Last trusted price ${formatPrice(target.current_price, target.current_currency)}.`;
        } else if (status.key === "stale") {
          copy = `Last trusted ${formatRelativeTime(eventTime)}.`;
        }
        items.push({
          product: bundle.product,
          competitor,
          status,
          copy,
          eventTime,
        });
      });
    });
    return items.sort((left, right) => {
      const priority = { failed: 0, stale: 1, waiting: 2 };
      return priority[left.status.key] - priority[right.status.key];
    });
  }

  function renderAttention(data) {
    const items = attentionItems(data);
    if (!items.length) {
      const competitorsById = competitorMap(data.competitors);
      const activeTargets = data.bundles.reduce(
        (count, bundle) =>
          count +
          bundle.targets.filter(
            (target) =>
              bundle.product.is_active &&
              target.is_active &&
              competitorsById.get(target.competitor_id)?.is_active !== false,
          ).length,
        0,
      );
      if (!activeTargets) {
        return `<div class="empty-state compact">
          <span class="pill waiting">No active checks</span>
          <h2>${data.products.length ? "Monitoring paused" : "No monitoring yet"}</h2>
          <p>${data.products.length ? "No active targets are scheduled." : "Add a product and competitor URL to begin."}</p>
        </div>`;
      }
      return `<div class="empty-state compact">
        <span class="pill success">All current</span>
        <h2>Nothing needs attention</h2>
        <p>Active targets are reporting within their expected schedule.</p>
      </div>`;
    }
    const visible = items.slice(0, 6);
    return `<ul class="attention-list">
      ${visible.map((item) => `<li class="attention-item">
        <div class="attention-copy">
          <a class="cell-title" href="${escapeHtml(productHref(item.product.id))}" data-nav>${escapeHtml(item.product.name)}</a>
          <p>${escapeHtml(item.competitor?.name || "Competitor")} · ${escapeHtml(item.copy)}</p>
        </div>
        <div class="attention-meta">
          ${statusPill(item.status)}
          ${item.eventTime ? `<time class="exact-time" datetime="${escapeHtml(item.eventTime)}">${escapeHtml(formatExactTime(item.eventTime))}</time>` : ""}
        </div>
      </li>`).join("")}
    </ul>`;
  }

  async function renderOverview() {
    main.innerHTML = loadingMarkup("Loading overview");
    const data = await loadMonitoringData();
    state.data = data;
    const attention = attentionItems(data);
    const activeCompetitors = competitorMap(data.competitors);
    const activeTargetCount = data.bundles.reduce(
      (count, bundle) =>
        count +
        bundle.targets.filter(
          (target) =>
            bundle.product.is_active &&
            target.is_active &&
            activeCompetitors.get(target.competitor_id)?.is_active !== false,
        ).length,
      0,
    );
    const trustedOffers = data.bundles.reduce(
      (count, bundle) => count + bundle.offers.filter((offer) => offer.price !== null).length,
      0,
    );
    const actions = `<a class="button primary" href="${escapeHtml(appHref("/products/new"))}" data-nav>Add product</a>`;
    main.innerHTML = `${pageHeading(
      state.customer.name,
      "Overview",
      "Trusted prices, changes, and monitoring health.",
      actions,
    )}
      ${partialNotice()}
      <section class="summary-strip" aria-label="Workspace summary">
        <span><strong>${data.products.length}</strong> product${data.products.length === 1 ? "" : "s"}</span>
        <span><strong>${trustedOffers}</strong> trusted offer${trustedOffers === 1 ? "" : "s"}</span>
        <span>${attention.length
          ? `<span class="pill warning">${attention.length} need attention</span>`
          : activeTargetCount
            ? '<span class="pill success">Monitoring current</span>'
            : '<span class="pill waiting">Nothing monitored</span>'}</span>
        <span class="summary-spacer"></span>
        <span class="exact-time">Loaded ${escapeHtml(formatExactTime(new Date().toISOString()))}</span>
      </section>
      <div class="workspace-grid">
        <section class="panel" aria-labelledby="prices-title">
          <div class="panel-heading">
            <div class="panel-heading-copy"><span class="eyebrow">Current</span><h2 id="prices-title">Monitored products</h2></div>
            <a class="text-link" href="${escapeHtml(appHref("/products"))}" data-nav>View all</a>
          </div>
          ${productTable(data, "overview-products")}
        </section>
        <section class="panel" aria-labelledby="attention-title">
          <div class="panel-heading">
            <div class="panel-heading-copy"><span class="eyebrow">Checks</span><h2 id="attention-title">Needs attention</h2></div>
            <span class="pill ${attention.length ? "warning" : "success"}">${attention.length}</span>
          </div>
          ${renderAttention(data)}
        </section>
      </div>`;
  }

  async function renderProducts() {
    main.innerHTML = loadingMarkup("Loading products");
    const data = await loadMonitoringData();
    state.data = data;
    const requestedCompetitor = safeId(new URLSearchParams(window.location.search).get("competitor"));
    const actions = `<a class="button primary" href="${escapeHtml(appHref("/products/new"))}" data-nav>Add product</a>`;
    main.innerHTML = `${pageHeading(
      state.customer.name,
      "Products",
      "Current offers and the latest accepted changes.",
      actions,
    )}
      ${partialNotice()}
      <div class="filters" aria-label="Product filters">
        <div class="filter-row" role="group" aria-label="Monitoring status">
          ${["all", "fresh", "changed", "attention"].map((filter) => `<button class="filter-button" type="button" data-action="product-filter" data-filter="${filter}" aria-pressed="${state.productFilter === filter}">${filter[0].toUpperCase()}${filter.slice(1)}</button>`).join("")}
        </div>
        <label class="search-input">
          <span class="sr-only">Search products</span>
          <input id="product-search" type="search" placeholder="Search products" value="${escapeHtml(state.search)}">
        </label>
      </div>
      <section class="panel" aria-labelledby="product-list-title">
        <div class="panel-heading">
          <div class="panel-heading-copy"><span class="eyebrow">Catalog</span><h2 id="product-list-title">All products</h2></div>
          <span class="pill" id="product-result-count">${data.products.length}</span>
        </div>
        ${productTable(data, "products-table")}
        <div class="empty-state compact" id="product-filter-empty" hidden>
          <h2>No matches</h2><p>Try another search or status.</p>
        </div>
      </section>`;
    applyProductFilters(requestedCompetitor);
  }

  function applyProductFilters(competitorId = "") {
    const table = document.querySelector("#products-table");
    if (!table) return;
    const rows = [...table.querySelectorAll("tbody tr")];
    const query = state.search.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const status = row.dataset.productState;
      const changed = Boolean(row.querySelector(".pill.increase, .pill.decrease"));
      const filterMatches =
        state.productFilter === "all" ||
        (state.productFilter === "fresh" && status === "fresh") ||
        (state.productFilter === "changed" && changed) ||
        (state.productFilter === "attention" && ["failed", "stale", "waiting"].includes(status));
      const searchMatches = !query || row.dataset.search.includes(query);
      const competitorMatches = !competitorId || row.dataset.competitors.split(" ").includes(competitorId);
      row.hidden = !(filterMatches && searchMatches && competitorMatches);
      if (!row.hidden) visible += 1;
    });
    const count = document.querySelector("#product-result-count");
    if (count) count.textContent = String(visible);
    const empty = document.querySelector("#product-filter-empty");
    if (empty) empty.hidden = visible !== 0;
  }

  function chartMarkup(bundle, competitorsById) {
    const currencyCounts = new Map();
    bundle.history.forEach((entry) => {
      if (entry.currency) {
        currencyCounts.set(entry.currency, (currencyCounts.get(entry.currency) || 0) + 1);
      }
    });
    const preferred = bundle.product.currency && currencyCounts.has(bundle.product.currency)
      ? bundle.product.currency
      : [...currencyCounts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0];
    const points = bundle.history
      .filter((entry) => entry.currency === preferred && Number.isFinite(Number(entry.price)))
      .map((entry) => ({ ...entry, timestamp: new Date(entry.observed_at).getTime(), numeric: Number(entry.price) }))
      .filter((entry) => Number.isFinite(entry.timestamp))
      .sort((left, right) => left.timestamp - right.timestamp);
    if (points.length < 2) {
      return emptyState(
        "Chart starts after 2 checks",
        "Accepted observations will appear here. Failed checks never enter the chart.",
      );
    }

    const width = 760;
    const height = 240;
    const margin = { top: 16, right: 18, bottom: 30, left: 62 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const minTime = points[0].timestamp;
    const maxTime = points.at(-1).timestamp;
    const values = points.map((point) => point.numeric);
    let minPrice = Math.min(...values);
    let maxPrice = Math.max(...values);
    const padding = Math.max((maxPrice - minPrice) * 0.12, maxPrice * 0.015, 0.01);
    minPrice -= padding;
    maxPrice += padding;
    const x = (timestamp) =>
      margin.left + ((timestamp - minTime) / Math.max(1, maxTime - minTime)) * plotWidth;
    const y = (price) =>
      margin.top + (1 - (price - minPrice) / Math.max(0.0001, maxPrice - minPrice)) * plotHeight;
    const groups = new Map();
    points.forEach((point) => {
      const valuesForTarget = groups.get(point.competitor_product_id) || [];
      valuesForTarget.push(point);
      groups.set(point.competitor_product_id, valuesForTarget);
    });
    const targetsById = new Map(bundle.targets.map((target) => [target.id, target]));
    const colors = ["#126b5b", "#17201a", "#7d6854", "#687169", "#8a514b"];
    const grid = [0, 1, 2, 3].map((index) => {
      const ratio = index / 3;
      const gridY = margin.top + ratio * plotHeight;
      const value = maxPrice - ratio * (maxPrice - minPrice);
      return `<line class="chart-grid" x1="${margin.left}" x2="${width - margin.right}" y1="${gridY.toFixed(1)}" y2="${gridY.toFixed(1)}"></line>
        <text class="chart-axis" x="${margin.left - 8}" y="${(gridY + 3).toFixed(1)}" text-anchor="end">${escapeHtml(formatChartPrice(value, preferred))}</text>`;
    }).join("");
    const lines = [...groups.entries()].map(([targetId, series], index) => {
      const color = colors[index % colors.length];
      const path = series.map((point, pointIndex) => `${pointIndex ? "L" : "M"}${x(point.timestamp).toFixed(1)},${y(point.numeric).toFixed(1)}`).join(" ");
      const markers = series.slice(-24).map((point) => `<rect class="chart-point" x="${(x(point.timestamp) - 3.5).toFixed(1)}" y="${(y(point.numeric) - 3.5).toFixed(1)}" width="7" height="7" rx="1" fill="${color}">
        <title>${escapeHtml(`${formatPrice(point.price, point.currency)} · ${formatExactTime(point.observed_at)}`)}</title>
      </rect>`).join("");
      return `<path class="chart-line" d="${path}" stroke="${color}"></path>${markers}`;
    }).join("");
    const legend = [...groups.keys()].map((targetId, index) => {
      const target = targetsById.get(targetId);
      const competitor = target ? competitorsById.get(target.competitor_id) : null;
      return `<span class="series-${index % colors.length}"><span class="legend-swatch"></span>${escapeHtml(competitor?.name || "Competitor")}</span>`;
    }).join("");

    return `<div class="chart-wrap">
      <svg class="price-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Accepted ${escapeHtml(preferred)} prices over time">
        ${grid}
        ${lines}
        <text class="chart-axis" x="${margin.left}" y="${height - 8}">${escapeHtml(formatExactTime(points[0].observed_at))}</text>
        <text class="chart-axis" x="${width - margin.right}" y="${height - 8}" text-anchor="end">${escapeHtml(formatExactTime(points.at(-1).observed_at))}</text>
      </svg>
      <div class="chart-legend"><span class="pill">${escapeHtml(preferred)}</span>${legend}</div>
    </div>`;
  }

  function offerRows(bundle, competitorsById) {
    const rows = [];
    if (bundle.product.current_own_price !== null && bundle.product.currency) {
      rows.push({
        key: "own",
        name: state.customer.name,
        price: bundle.product.current_own_price,
        currency: bundle.product.currency,
        availability: null,
        observedAt: bundle.product.updated_at,
        url: bundle.product.customer_product_url,
        status: { key: "manual", label: "Own price", tone: "" },
        target: null,
      });
    }
    bundle.offers.forEach((offer) => {
      const target = bundle.targets.find((item) => item.id === offer.competitor_product_id);
      const competitor = competitorsById.get(offer.competitor_id);
      rows.push({
        key: offer.competitor_product_id,
        name: offer.competitor_name,
        price: offer.price,
        currency: offer.currency,
        availability: offer.availability,
        observedAt: offer.observed_at,
        url: offer.product_url,
        status: target
          ? targetStatus(target, competitor, bundle.latestResults[target.id])
          : { key: "waiting", label: "Status unavailable", tone: "waiting" },
        target,
      });
    });

    const lowestByCurrency = new Map();
    rows.forEach((row) => {
      if (!row.currency || !Number.isFinite(Number(row.price))) return;
      const current = lowestByCurrency.get(row.currency);
      if (!current || Number(row.price) < Number(current.price)) lowestByCurrency.set(row.currency, row);
    });
    rows.sort((left, right) => {
      if (!left.currency || !right.currency) return left.currency ? -1 : 1;
      if (left.currency !== right.currency) return left.currency.localeCompare(right.currency);
      return Number(left.price ?? Infinity) - Number(right.price ?? Infinity);
    });

    return rows.map((row) => {
      const link = safeExternalUrl(row.url);
      const isLowest = row.currency && lowestByCurrency.get(row.currency)?.key === row.key;
      const availability = row.availability
        ? `<span class="pill">${escapeHtml(row.availability.replaceAll("_", " "))}</span>`
        : "";
      return `<tr>
        <td><span class="cell-title">${escapeHtml(row.name)}</span>${row.key === "own" ? '<span class="cell-subtitle">Your store</span>' : ""}</td>
        <td><span class="price">${escapeHtml(formatPrice(row.price, row.currency))}</span></td>
        <td><div class="button-row">${isLowest ? '<span class="pill accent">Lowest price</span>' : ""}${availability}</div></td>
        <td>${statusPill(row.status)}</td>
        <td>${timeMarkup(row.observedAt, ["failed", "stale"].includes(row.status.key) ? row.status.tone : "")}</td>
        <td><div class="button-row">
          ${link ? `<a class="button small" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Open</a>` : ""}
          ${row.target ? `<button class="button small" type="button" data-action="check-now" data-target-id="${escapeHtml(row.target.id)}">Check now</button>` : ""}
        </div></td>
      </tr>`;
    }).join("");
  }

  function historyRows(bundle, competitorsById) {
    if (!bundle.history.length) {
      return `<tr><td colspan="4">${emptyState("No accepted history", "Run a check to record the first trusted price.")}</td></tr>`;
    }
    const targetsById = new Map(bundle.targets.map((target) => [target.id, target]));
    return bundle.history.slice(0, 20).map((entry) => {
      const target = targetsById.get(entry.competitor_product_id);
      const competitor = target ? competitorsById.get(target.competitor_id) : null;
      return `<tr>
        <td><span class="cell-title">${escapeHtml(competitor?.name || "Competitor")}</span></td>
        <td><span class="price">${escapeHtml(formatPrice(entry.price, entry.currency))}</span></td>
        <td>${changeMarkup(entry)}</td>
        <td>${timeMarkup(entry.observed_at)}</td>
      </tr>`;
    }).join("");
  }

  function addCompetitorUrlPanel(bundle, competitors) {
    const connected = new Set(bundle.targets.map((target) => target.competitor_id));
    const available = competitors.filter((competitor) => competitor.is_active && !connected.has(competitor.id));
    if (!available.length) {
      return `<div class="empty-state compact">
        <h2>All sources connected</h2>
        <p>Add another configured competitor before connecting another URL.</p>
        <a class="button" href="${escapeHtml(appHref("/competitors"))}" data-nav>View competitors</a>
      </div>`;
    }
    return `<form id="add-offer-form" novalidate>
      <fieldset>
        <legend>Add competitor URL</legend>
        <div class="field-grid">
          <div class="field full">
            <label for="offer-competitor">Competitor <span class="required">Required</span></label>
            <select id="offer-competitor" name="competitor_id" required>
              ${available.map((competitor) => `<option value="${escapeHtml(competitor.id)}">${escapeHtml(competitor.name)}</option>`).join("")}
            </select>
          </div>
          <div class="field full">
            <label for="offer-url">Product URL <span class="required">Required</span></label>
            <input id="offer-url" name="product_url" type="url" inputmode="url" autocomplete="url" required placeholder="https://competitor.example/product">
            <span class="help">The hostname must match the configured competitor.</span>
          </div>
        </div>
      </fieldset>
      <div class="form-actions">
        <span class="form-status">A first check is queued after saving.</span>
        <button class="button primary" type="submit">Add URL</button>
      </div>
    </form>`;
  }

  async function renderProductDetail(productId) {
    main.innerHTML = loadingMarkup("Loading product");
    const [product, competitors] = await Promise.all([
      request(`/products/${safeId(productId)}`, { kind: "product" }),
      optionalRequest(`/customers/${selectedCustomerId()}/competitors`, [], "competitors"),
    ]);
    if (product.customer_id !== selectedCustomerId()) throw new ApiError(404, "product");
    const bundle = await loadProductBundle(product);
    state.data = { product, competitors, bundle };
    const competitorsById = competitorMap(competitors);
    const trustedTime = latestTrustedTime(bundle);
    const productState = productStatus(bundle, competitorsById);
    const actions = `<a class="button" href="${escapeHtml(appHref("/products"))}" data-nav>Back to products</a>`;
    main.innerHTML = `<nav class="breadcrumb" aria-label="Breadcrumb">
      <a href="${escapeHtml(appHref("/products"))}" data-nav>Products</a><span aria-hidden="true">/</span><span>${escapeHtml(product.name)}</span>
    </nav>
      ${pageHeading(state.customer.name, product.name, product.sku || "No SKU", actions)}
      ${partialNotice()}
      <section class="summary-strip" aria-label="Product summary">
        <span class="price">${escapeHtml(formatPrice(product.current_own_price, product.currency))}</span>
        ${statusPill(productState)}
        <span><strong>${bundle.offers.length}</strong> competitor offer${bundle.offers.length === 1 ? "" : "s"}</span>
        <span class="summary-spacer"></span>
        ${trustedTime ? `<span class="exact-time">Last trusted ${escapeHtml(formatExactTime(trustedTime))}</span>` : '<span class="exact-time">No trusted observation</span>'}
      </section>
      <div class="stack">
        <section class="panel" aria-labelledby="offers-title">
          <div class="panel-heading">
            <div class="panel-heading-copy"><span class="eyebrow">Comparison</span><h2 id="offers-title">All offers</h2></div>
            <span class="pill">Lowest marked per currency</span>
          </div>
          ${bundle.offers.length || product.current_own_price !== null ? `<div class="table-wrap"><table>
            <caption class="sr-only">Own and competitor offers</caption>
            <thead><tr><th scope="col">Seller</th><th scope="col">Price</th><th scope="col">Position</th><th scope="col">Status</th><th scope="col">Last trusted</th><th scope="col">Actions</th></tr></thead>
            <tbody>${offerRows(bundle, competitorsById)}</tbody>
          </table></div>` : emptyState("No offers", "Add a competitor URL to begin comparing prices.")}
        </section>
        <div class="workspace-grid">
          <section class="panel" aria-labelledby="chart-title">
            <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">History</span><h2 id="chart-title">Accepted prices</h2></div><span class="pill">Trusted only</span></div>
            ${chartMarkup(bundle, competitorsById)}
          </section>
          <section class="panel" aria-labelledby="connect-title">
            <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Monitor</span><h2 id="connect-title">Competitor URL</h2></div></div>
            ${addCompetitorUrlPanel(bundle, competitors)}
          </section>
        </div>
        <section class="panel" aria-labelledby="history-title">
          <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Changes</span><h2 id="history-title">Price history</h2></div><span class="pill">${bundle.history.length}</span></div>
          <div class="table-wrap"><table>
            <caption class="sr-only">Accepted price observations</caption>
            <thead><tr><th scope="col">Competitor</th><th scope="col">Price</th><th scope="col">Change</th><th scope="col">Observed</th></tr></thead>
            <tbody>${historyRows(bundle, competitorsById)}</tbody>
          </table></div>
        </section>
      </div>`;
  }

  function productFormMarkup(competitors) {
    const activeCompetitors = competitors.filter((competitor) => competitor.is_active);
    const unavailable = activeCompetitors.length === 0;
    return `<div class="workspace-grid">
      <section class="panel" aria-labelledby="new-product-title">
        <div class="panel-heading">
          <div class="panel-heading-copy"><span class="eyebrow">Catalog</span><h2 id="new-product-title">Product and competitor</h2></div>
          <span class="pill accent">One setup</span>
        </div>
        ${unavailable ? `<div class="notice warning"><strong>No configured competitor.</strong> Add one before starting product monitoring.</div>` : ""}
        <form id="product-form" novalidate>
          <fieldset>
            <legend>Product</legend>
            <div class="field-grid">
              <div class="field full">
                <label for="product-name">Name <span class="required">Required</span></label>
                <input id="product-name" name="name" maxlength="500" autocomplete="off" required autofocus>
              </div>
              <div class="field">
                <label for="product-sku">SKU</label>
                <input id="product-sku" name="sku" maxlength="200" autocomplete="off">
              </div>
              <div class="field">
                <label for="own-price">Own price</label>
                <input id="own-price" name="current_own_price" type="number" inputmode="decimal" min="0.0001" step="0.0001" placeholder="0.00">
              </div>
              <div class="field full">
                <label for="own-url">Own product URL</label>
                <input id="own-url" name="customer_product_url" type="url" inputmode="url" autocomplete="url" placeholder="https://your-store.example/product">
              </div>
              <div class="field">
                <label for="own-currency">Currency</label>
                <input id="own-currency" name="currency" minlength="3" maxlength="3" pattern="[A-Za-z]{3}" autocomplete="off" value="${escapeHtml(state.customer.default_currency || "")}">
                <span class="help">Required with an own price.</span>
              </div>
            </div>
          </fieldset>
          <fieldset ${unavailable ? "disabled" : ""}>
            <legend>Competitor URL</legend>
            <div class="field-grid">
              <div class="field">
                <label for="new-product-competitor">Competitor <span class="required">Required</span></label>
                <select id="new-product-competitor" name="competitor_id" required>
                  ${unavailable ? '<option value="">Unavailable</option>' : activeCompetitors.map((competitor) => `<option value="${escapeHtml(competitor.id)}">${escapeHtml(competitor.name)}</option>`).join("")}
                </select>
              </div>
              <div class="field full">
                <label for="competitor-url">Product URL <span class="required">Required</span></label>
                <input id="competitor-url" name="product_url" type="url" inputmode="url" autocomplete="url" required placeholder="https://competitor.example/product">
                <span class="help">The hostname must match the selected competitor.</span>
              </div>
            </div>
          </fieldset>
          <div class="form-actions">
            <span class="form-status">The first check is queued automatically.</span>
            <a class="button" href="${escapeHtml(appHref("/products"))}" data-nav>Cancel</a>
            <button class="button primary" type="submit" ${unavailable ? 'disabled data-permanent-disabled="true"' : ""}>Add product</button>
          </div>
        </form>
      </section>
      <aside class="panel" aria-labelledby="setup-title">
        <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Setup</span><h2 id="setup-title">What happens next</h2></div></div>
        <ol class="plain-list">
          <li><div><h3>Product saved</h3><span class="muted">Your catalog record is created.</span></div><span class="pill">1</span></li>
          <li><div><h3>URL connected</h3><span class="muted">The competitor offer is mapped.</span></div><span class="pill">2</span></li>
          <li><div><h3>Check queued</h3><span class="muted">A worker records the first trusted price.</span></div><span class="pill">3</span></li>
        </ol>
        ${unavailable ? `<div class="panel-body"><a class="button primary" href="${escapeHtml(appHref("/competitors"))}" data-nav>Configure competitor</a></div>` : ""}
      </aside>
    </div>`;
  }

  async function renderAddProduct() {
    main.innerHTML = loadingMarkup("Loading product setup");
    const { competitors } = await loadCoreData();
    state.data = { competitors };
    main.innerHTML = `<nav class="breadcrumb" aria-label="Breadcrumb">
      <a href="${escapeHtml(appHref("/products"))}" data-nav>Products</a><span aria-hidden="true">/</span><span>Add product</span>
    </nav>
      ${pageHeading(state.customer.name, "Add product", "Save a product, connect one competitor, and start checking.")}
      ${partialNotice()}
      ${productFormMarkup(competitors)}`;
  }

  async function loadCompetitorData() {
    const core = await loadCoreData();
    const [bundles, adapters] = await Promise.all([
      Promise.all(core.products.map((product) => loadProductBundle(product, { history: false, offers: false, results: false }))),
      optionalRequest("/adapters", [], "source adapters", { allow404: true }),
    ]);
    const health = {};
    await Promise.all(
      core.competitors.map(async (competitor) => {
        health[competitor.id] = await optionalRequest(
          `/competitors/${safeId(competitor.id)}/health-summary`,
          null,
          "scraper health",
          { allow404: true },
        );
      }),
    );
    return { ...core, bundles, adapters, health };
  }

  function competitorDisplayStatus(competitor, health) {
    if (!competitor.is_active || health?.status === "disabled") {
      return { key: "paused", label: "Paused", tone: "" };
    }
    if (!health?.last_attempt_at) return { key: "waiting", label: "Not checked", tone: "waiting" };
    if (health.status === "healthy") {
      const age = (Date.now() - new Date(health.last_success_at).getTime()) / 1000;
      if (Number.isFinite(age) && age > Number(competitor.schedule_interval_seconds) * 2) {
        return { key: "stale", label: "Stale", tone: "stale" };
      }
      return { key: "fresh", label: "Healthy", tone: "fresh" };
    }
    if (["repair_queued", "repairing"].includes(health?.status)) {
      return { key: "checking", label: health.status === "repairing" ? "Repairing" : "Repair queued", tone: "checking" };
    }
    return { key: "failed", label: health?.status === "broken" ? "Broken" : "Degraded", tone: "failed" };
  }

  function competitorTableRows(data) {
    const targets = data.bundles.flatMap((bundle) => bundle.targets);
    return data.competitors.map((competitor) => {
      const health = data.health[competitor.id];
      const status = competitorDisplayStatus(competitor, health);
      const mapped = targets.filter((target) => target.competitor_id === competitor.id);
      const viewHref = appHref("/products", { competitor: competitor.id });
      return `<tr data-competitor-state="${escapeHtml(status.key)}">
        <td><span class="cell-title">${escapeHtml(competitor.name)}</span><span class="cell-subtitle">${escapeHtml(formatHost(competitor.base_url))}</span></td>
        <td><a class="text-link" href="${escapeHtml(viewHref)}" data-nav>${mapped.length} product${mapped.length === 1 ? "" : "s"}</a></td>
        <td>${statusPill(status)}</td>
        <td><span class="price">${Number(health?.recent_failure_count || 0)}</span></td>
        <td>${timeMarkup(health?.last_success_at, status.key === "stale" ? "stale" : "")}</td>
        <td><span class="pill">${escapeHtml(formatInterval(competitor.schedule_interval_seconds))}</span></td>
      </tr>`;
    }).join("");
  }

  function competitorSetupPanel(adapters) {
    if (!adapters.length) {
      return `<div class="empty-state compact">
        <span class="pill waiting">Unavailable</span>
        <h2>No source adapter</h2>
        <p>An operator must install a trusted source adapter before adding a competitor.</p>
      </div>`;
    }
    return `<form id="competitor-form" novalidate>
      <fieldset>
        <legend>Add competitor</legend>
        <div class="field-grid">
          <div class="field full">
            <label for="competitor-name">Name <span class="required">Required</span></label>
            <input id="competitor-name" name="name" maxlength="200" required>
          </div>
          <div class="field full">
            <label for="competitor-adapter">Trusted source <span class="required">Required</span></label>
            <select id="competitor-adapter" name="adapter_key" required>
              ${adapters.map((adapter) => `<option value="${escapeHtml(adapter.key)}" data-fetch-mode="${escapeHtml(adapter.fetch_mode)}" data-hosts="${escapeHtml(adapter.allowed_hosts.join(", "))}">${escapeHtml(adapter.display_name)}</option>`).join("")}
            </select>
            <span class="help" id="adapter-hosts">Allowed: ${escapeHtml(adapters[0].allowed_hosts.join(", "))}</span>
          </div>
          <div class="field full">
            <label for="competitor-base-url">Base URL <span class="required">Required</span></label>
            <input id="competitor-base-url" name="base_url" type="url" inputmode="url" autocomplete="url" required placeholder="https://competitor.example">
          </div>
          <div class="field">
            <label for="competitor-currency">Currency</label>
            <input id="competitor-currency" name="expected_currency" minlength="3" maxlength="3" pattern="[A-Za-z]{3}" value="${escapeHtml(state.customer.default_currency || "")}">
          </div>
        </div>
      </fieldset>
      <div class="form-actions"><button class="button primary" type="submit">Add competitor</button></div>
    </form>`;
  }

  async function renderCompetitors() {
    main.innerHTML = loadingMarkup("Loading competitors");
    const data = await loadCompetitorData();
    state.data = data;
    main.innerHTML = `${pageHeading(state.customer.name, "Competitors", "Configured sources and scraper health.")}
      ${partialNotice()}
      <div class="filters">
        <div class="filter-row" role="group" aria-label="Competitor health">
          ${["all", "healthy", "attention"].map((filter) => `<button class="filter-button" type="button" data-action="competitor-filter" data-filter="${filter}" aria-pressed="${state.competitorFilter === filter}">${filter[0].toUpperCase()}${filter.slice(1)}</button>`).join("")}
        </div>
      </div>
      <div class="workspace-grid">
        <section class="panel" aria-labelledby="competitor-list-title">
          <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Sources</span><h2 id="competitor-list-title">Monitoring health</h2></div><span class="pill" id="competitor-result-count">${data.competitors.length}</span></div>
          ${data.competitors.length ? `<div class="table-wrap"><table id="competitors-table">
            <caption class="sr-only">Competitors and scraper health</caption>
            <thead><tr><th scope="col">Competitor</th><th scope="col">URLs</th><th scope="col">Health</th><th scope="col">Failures</th><th scope="col">Last success</th><th scope="col">Schedule</th></tr></thead>
            <tbody>${competitorTableRows(data)}</tbody>
          </table></div><div class="empty-state compact" id="competitor-filter-empty" hidden><h2>No matches</h2><p>Try another status.</p></div>` : emptyState("No competitors", "Add a trusted source before connecting product URLs.")}
        </section>
        <aside class="panel" aria-labelledby="add-competitor-title">
          <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Setup</span><h2 id="add-competitor-title">New competitor</h2></div></div>
          ${competitorSetupPanel(data.adapters)}
        </aside>
      </div>`;
    applyCompetitorFilters();
  }

  function applyCompetitorFilters() {
    const table = document.querySelector("#competitors-table");
    if (!table) return;
    let visible = 0;
    table.querySelectorAll("tbody tr").forEach((row) => {
      const status = row.dataset.competitorState;
      const matches =
        state.competitorFilter === "all" ||
        (state.competitorFilter === "healthy" && status === "fresh") ||
        (state.competitorFilter === "attention" && ["failed", "stale", "waiting"].includes(status));
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    const count = document.querySelector("#competitor-result-count");
    if (count) count.textContent = String(visible);
    const empty = document.querySelector("#competitor-filter-empty");
    if (empty) empty.hidden = visible !== 0;
  }

  function alertState(rule) {
    const evaluation = rule.evaluation || {};
    const key = evaluation.state || (rule.is_active ? "waiting" : "disabled");
    const values = {
      disabled: { key, label: "Paused", tone: "" },
      waiting: { key, label: "Waiting", tone: "waiting" },
      clear: { key, label: "Clear", tone: "fresh" },
      triggered: { key, label: "Triggered", tone: "triggered" },
    };
    return values[key] || values.waiting;
  }

  function alertCondition(rule) {
    const direction = {
      either: "Price moves",
      increase: "Price increases",
      decrease: "Price decreases",
    }[rule.direction] || "Price moves";
    return `${direction} by ${formatPercent(rule.threshold_percent, false)} or more`;
  }

  function alertRuleRows(rules, productsById) {
    return rules.map((rule) => {
      const product = productsById.get(rule.product_id);
      const evaluation = rule.evaluation || {};
      const displayState = alertState(rule);
      const activeLabel = rule.is_active ? "Pause" : "Resume";
      return `<tr>
        <td>
          <a class="cell-title" href="${escapeHtml(productHref(rule.product_id))}" data-nav>${escapeHtml(product?.name || "Unavailable product")}</a>
          <span class="cell-subtitle">${escapeHtml(alertCondition(rule))}</span>
        </td>
        <td>${statusPill(displayState)}</td>
        <td>${evaluation.change_percent !== null && evaluation.change_percent !== undefined ? changeMarkup({ change_kind: Number(evaluation.change_percent) < 0 ? "decrease" : "increase", change_percent: evaluation.change_percent }) : '<span class="muted">No match</span>'}</td>
        <td>${timeMarkup(evaluation.last_checked_at)}</td>
        <td><div class="button-row">
          <button class="button small" type="button" data-action="toggle-alert" data-alert-id="${escapeHtml(rule.id)}" data-alert-active="${String(rule.is_active)}">${activeLabel}</button>
          <button class="button small danger" type="button" data-action="delete-alert" data-alert-id="${escapeHtml(rule.id)}">Remove</button>
        </div></td>
      </tr>`;
    }).join("");
  }

  function triggeredAlertList(rules, productsById) {
    const triggered = rules.filter((rule) => rule.evaluation?.state === "triggered" && rule.is_active);
    if (!triggered.length) return "";
    return `<section class="panel" aria-labelledby="triggered-alerts-title">
      <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Attention</span><h2 id="triggered-alerts-title">Triggered alerts</h2></div><span class="pill triggered">${triggered.length}</span></div>
      <ul class="attention-list">
        ${triggered.map((rule) => {
          const evaluation = rule.evaluation;
          const product = productsById.get(rule.product_id);
          return `<li class="attention-item">
            <div class="attention-copy">
              <a class="cell-title" href="${escapeHtml(productHref(rule.product_id))}" data-nav>${escapeHtml(product?.name || "Unavailable product")}</a>
              <p>${escapeHtml(alertCondition(rule))} · ${escapeHtml(formatPrice(evaluation.price, evaluation.currency))}</p>
            </div>
            <div class="attention-meta">${changeMarkup({ change_kind: Number(evaluation.change_percent) < 0 ? "decrease" : "increase", change_percent: evaluation.change_percent })}${timeMarkup(evaluation.last_triggered_at)}</div>
          </li>`;
        }).join("")}
      </ul>
    </section>`;
  }

  function alertForm(products) {
    const activeProducts = products.filter((product) => product.is_active);
    if (!activeProducts.length) {
      return emptyState(
        "No products",
        "Add a product before creating an alert.",
        `<a class="button primary" href="${escapeHtml(appHref("/products/new"))}" data-nav>Add product</a>`,
      );
    }
    return `<form id="alert-form" novalidate>
      <fieldset>
        <legend>New alert</legend>
        <div class="field-grid">
          <div class="field full">
            <label for="alert-product">Product <span class="required">Required</span></label>
            <select id="alert-product" name="product_id" required>
              ${activeProducts.map((product) => `<option value="${escapeHtml(product.id)}">${escapeHtml(product.name)}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="alert-direction">Change</label>
            <select id="alert-direction" name="direction">
              <option value="either">Any change</option>
              <option value="decrease">Decrease</option>
              <option value="increase">Increase</option>
            </select>
          </div>
          <div class="field">
            <label for="alert-threshold">Threshold</label>
            <input id="alert-threshold" name="threshold_percent" type="number" inputmode="decimal" min="0.1" step="0.1" value="5" required>
            <span class="help">Percent change.</span>
          </div>
        </div>
      </fieldset>
      <div class="form-actions"><button class="button primary" type="submit">Create alert</button></div>
    </form>`;
  }

  async function renderAlerts() {
    main.innerHTML = loadingMarkup("Loading alerts");
    const core = await loadCoreData();
    const rules = await optionalRequest(
      `/customers/${selectedCustomerId()}/alert-rules`,
      [],
      "alert rules",
    );
    state.data = { ...core, rules };
    const productsById = new Map(core.products.map((product) => [product.id, product]));
    main.innerHTML = `${pageHeading(state.customer.name, "Alerts", "Important accepted price changes.")}
      ${partialNotice()}
      <section class="summary-strip" aria-label="Alert status">
        <span><strong>${rules.length}</strong> rule${rules.length === 1 ? "" : "s"}</span>
        <span><span class="pill accent">In-app</span></span>
        <span class="muted">Email delivery unavailable</span>
      </section>
      <div class="stack">
        ${triggeredAlertList(rules, productsById)}
        <div class="workspace-grid">
          <section class="panel" aria-labelledby="alert-rules-title">
            <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Rules</span><h2 id="alert-rules-title">Price alerts</h2></div><span class="pill">${rules.length}</span></div>
            ${rules.length ? `<div class="table-wrap"><table>
              <caption class="sr-only">Configured in-app price alert rules</caption>
              <thead><tr><th scope="col">Rule</th><th scope="col">State</th><th scope="col">Latest match</th><th scope="col">Checked</th><th scope="col">Actions</th></tr></thead>
              <tbody>${alertRuleRows(rules, productsById)}</tbody>
            </table></div>` : emptyState("No alerts", "Create one rule for an important price move.")}
          </section>
          <aside class="panel" aria-labelledby="new-alert-title">
            <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Configure</span><h2 id="new-alert-title">Add rule</h2></div></div>
            ${alertForm(core.products)}
          </aside>
        </div>
      </div>`;
  }

  function workspaceSetupMarkup() {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    return `${pageHeading("First setup", "Create workspace", "Add your store before monitoring competitor prices.")}
      <div class="workspace-grid">
        <section class="panel" aria-labelledby="workspace-form-title">
          <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Workspace</span><h2 id="workspace-form-title">Store details</h2></div></div>
          <form id="workspace-form" novalidate>
            <fieldset>
              <legend>Your store</legend>
              <div class="field-grid">
                <div class="field full"><label for="workspace-name">Name <span class="required">Required</span></label><input id="workspace-name" name="name" maxlength="200" required autofocus></div>
                <div class="field"><label for="workspace-slug">Short name <span class="required">Required</span></label><input id="workspace-slug" name="slug" maxlength="100" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required><span class="help">Lowercase letters and dashes.</span></div>
                <div class="field"><label for="workspace-currency">Currency</label><input id="workspace-currency" name="default_currency" value="USD" minlength="3" maxlength="3" pattern="[A-Za-z]{3}" required></div>
                <div class="field full"><label for="workspace-url">Store URL <span class="required">Required</span></label><input id="workspace-url" name="webshop_url" type="url" inputmode="url" autocomplete="url" required placeholder="https://your-store.example"></div>
                <input name="timezone" type="hidden" value="${escapeHtml(timezone)}">
              </div>
            </fieldset>
            <div class="form-actions"><button class="button primary" type="submit">Create workspace</button></div>
          </form>
        </section>
        <aside class="panel"><div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Next</span><h2>Configure one competitor</h2></div></div><div class="panel-body"><p class="muted">Then add a product and its matching competitor URL.</p><span class="pill">About 2 minutes</span></div></aside>
      </div>`;
  }

  async function sessionRequest(method = "GET", accessKey = null) {
    const headers = { Accept: "application/json" };
    const options = {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers,
      signal: state.controller?.signal,
    };
    if (method !== "GET") headers["X-Price-Monitor-UI"] = "1";
    if (accessKey !== null) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify({ access_key: accessKey });
    }
    let response;
    try {
      response = await fetch("/session", options);
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new ApiError(0, "session");
    }
    if (!response.ok) throw new ApiError(response.status, "session");
    try {
      return await response.json();
    } catch (_error) {
      throw new ApiError(502, "session");
    }
  }

  function updateSessionControl() {
    sessionLogout.hidden = !(state.session?.protected && state.session?.authenticated);
  }

  function renderAccess(error = "") {
    state.customers = [];
    state.customer = null;
    updateHeader(parseRoute());
    updateSessionControl();
    document.title = "Access required · Price Monitor";
    main.innerHTML = `<div class="workspace-grid access-layout">
      <section class="panel" aria-labelledby="access-title">
        <div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Protected workspace</span><h2 id="access-title">Operator access</h2></div><span class="pill">Private</span></div>
        ${error ? `<div class="notice error" role="alert">${escapeHtml(error)}</div>` : ""}
        <form id="session-form" novalidate>
          <fieldset>
            <legend>Access key</legend>
            <div class="field full">
              <label for="access-key">Access key <span class="required">Required</span></label>
              <input id="access-key" name="access_key" type="password" autocomplete="current-password" autocapitalize="none" spellcheck="false" required autofocus>
              <span class="help">Used once to create a secure browser session. It is never stored in this page.</span>
            </div>
          </fieldset>
          <div class="form-actions"><button class="button primary" type="submit">Continue</button></div>
        </form>
      </section>
      <aside class="panel"><div class="panel-heading"><div class="panel-heading-copy"><span class="eyebrow">Security</span><h2>Your key stays private</h2></div></div><div class="panel-body"><p class="muted">Price Monitor uses a protected, same-site session. Signing out clears it.</p></div></aside>
    </div>`;
    main.removeAttribute("aria-busy");
  }

  function renderMissing() {
    main.innerHTML = `<div class="error-state">
      <span class="eyebrow">Not found</span>
      <h1>This page is unavailable</h1>
      <p>The address may be old or incomplete.</p>
      <a class="button primary" href="${escapeHtml(appHref("/"))}" data-nav>Back to overview</a>
    </div>`;
  }

  function renderMissingProduct() {
    document.title = "Product not found · Price Monitor";
    main.innerHTML = `<div class="error-state" role="alert">
      <span class="eyebrow">Product not found</span>
      <h1>This product is unavailable</h1>
      <p>It may have been removed or belongs to another workspace.</p>
      <div class="button-row">
        <a class="button primary" href="${escapeHtml(appHref("/products"))}" data-nav>Back to products</a>
        <a class="button" href="${escapeHtml(appHref("/"))}" data-nav>Overview</a>
      </div>
    </div>`;
    main.removeAttribute("aria-busy");
  }

  async function renderRoute({ focus = false } = {}) {
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    state.partialErrors = [];
    state.data = null;
    state.route = parseRoute();
    main.setAttribute("aria-busy", "true");
    main.innerHTML = loadingMarkup(`Loading ${titleForRoute(state.route).toLowerCase()}`);
    document.title = `${titleForRoute(state.route)} · Price Monitor`;
    try {
      state.session = await sessionRequest();
      updateSessionControl();
      if (state.session.protected && !state.session.authenticated) {
        renderAccess();
        return;
      }

      await loadCustomers();
      updateHeader(state.route);
      if (!state.customer) {
        document.title = "Create workspace · Price Monitor";
        main.innerHTML = workspaceSetupMarkup();
        main.removeAttribute("aria-busy");
        return;
      }

      const query = new URLSearchParams(window.location.search);
      if (query.get("customer") !== state.customer.id) {
        query.set("customer", state.customer.id);
        const next = `${window.location.pathname}?${query.toString()}`;
        window.history.replaceState({}, "", next);
      }

      if (state.route.name === "overview") await renderOverview();
      else if (state.route.name === "products") await renderProducts();
      else if (state.route.name === "add-product") await renderAddProduct();
      else if (state.route.name === "product-detail") {
        await renderProductDetail(state.route.productId);
        if (state.data?.product) document.title = `${state.data.product.name} · Price Monitor`;
      } else if (state.route.name === "competitors") await renderCompetitors();
      else if (state.route.name === "alerts") await renderAlerts();
      else renderMissing();
      main.removeAttribute("aria-busy");
      if (focus) main.focus({ preventScroll: true });
    } catch (error) {
      if (error?.name === "AbortError") return;
      if (error?.status === 404 && state.route?.name === "product-detail") {
        renderMissingProduct();
        if (focus) main.focus({ preventScroll: true });
        return;
      }
      if ((error?.status === 401 || error?.status === 403) && state.session?.protected) {
        state.session.authenticated = false;
        renderAccess("Your session ended. Enter the access key again.");
        return;
      }
      renderFatal(error);
    }
  }

  async function navigate(href, options = {}) {
    const url = new URL(href, window.location.origin);
    window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    await renderRoute({ focus: options.focus !== false });
  }

  async function submitSession(form) {
    if (!form.reportValidity()) return;
    const field = form.querySelector("#access-key");
    const accessKey = field.value;
    setFormBusy(form, true, "Checking");
    try {
      const result = await sessionRequest("POST", accessKey);
      field.value = "";
      state.session = result;
      if (!result.authenticated) throw new ApiError(401, "session");
      await renderRoute({ focus: true });
    } catch (error) {
      field.value = "";
      setFormBusy(form, false);
      renderAccess(error?.status === 401 ? "Access key not accepted." : "Could not start a secure session.");
    }
  }

  async function submitWorkspace(form) {
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const payload = {
      name: String(data.get("name") || "").trim(),
      slug: String(data.get("slug") || "").trim().toLowerCase(),
      webshop_url: String(data.get("webshop_url") || "").trim(),
      default_currency: String(data.get("default_currency") || "USD").trim().toUpperCase(),
      timezone: String(data.get("timezone") || "UTC"),
    };
    setFormBusy(form, true, "Creating");
    try {
      const customer = await request("/customers", { method: "POST", body: payload, kind: "workspace" });
      await navigate(`/?customer=${encodeURIComponent(customer.id)}`);
      showToast("Workspace created.");
    } catch (error) {
      setFormBusy(form, false);
      showToast(safeActionMessage(error, "Workspace"), "error");
    }
  }

  function readProductPayload(data) {
    const payload = { name: String(data.get("name") || "").trim() };
    const sku = String(data.get("sku") || "").trim();
    const ownUrl = String(data.get("customer_product_url") || "").trim();
    const price = String(data.get("current_own_price") || "").trim();
    const currency = String(data.get("currency") || "").trim().toUpperCase();
    if (sku) payload.sku = sku;
    if (ownUrl) payload.customer_product_url = ownUrl;
    if (price) {
      payload.current_own_price = price;
      payload.currency = currency;
    }
    return payload;
  }

  async function submitProduct(form) {
    const price = form.querySelector("#own-price");
    const currency = form.querySelector("#own-currency");
    currency.setCustomValidity(price.value && !currency.value.trim() ? "Enter a currency." : "");
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const productPayload = readProductPayload(data);
    const competitorId = safeId(data.get("competitor_id"));
    const competitorUrl = String(data.get("product_url") || "").trim();
    setFormBusy(form, true, "Adding");
    let product = null;
    let target = null;
    try {
      product = await request(`/customers/${selectedCustomerId()}/products`, {
        method: "POST",
        body: productPayload,
        kind: "product",
      });
      const competitor = state.data.competitors.find((item) => item.id === competitorId);
      target = await request(`/products/${safeId(product.id)}/competitor-products`, {
        method: "POST",
        body: {
          competitor_id: competitorId,
          product_url: competitorUrl,
          expected_name: product.name,
          expected_currency: competitor?.expected_currency || product.currency || state.customer.default_currency,
        },
        kind: "competitor URL",
      });
      await request(`/competitor-products/${safeId(target.id)}/scrapes`, {
        method: "POST",
        kind: "first check",
      });
      await navigate(productHref(product.id));
      showToast("Product added. First check queued.");
    } catch (error) {
      if (product) {
        await navigate(productHref(product.id));
        showToast(
          target
            ? "Product and URL saved. First check needs attention."
            : "Product saved. Add the competitor URL from this page.",
          "error",
        );
        return;
      }
      setFormBusy(form, false);
      showToast(safeActionMessage(error, "Product"), "error");
    }
  }

  async function submitOffer(form) {
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const competitorId = safeId(data.get("competitor_id"));
    const competitor = state.data.competitors.find((item) => item.id === competitorId);
    const product = state.data.product;
    setFormBusy(form, true, "Adding");
    try {
      const target = await request(`/products/${safeId(product.id)}/competitor-products`, {
        method: "POST",
        body: {
          competitor_id: competitorId,
          product_url: String(data.get("product_url") || "").trim(),
          expected_name: product.name,
          expected_currency: competitor?.expected_currency || product.currency || state.customer.default_currency,
        },
        kind: "competitor URL",
      });
      let queued = true;
      try {
        await request(`/competitor-products/${safeId(target.id)}/scrapes`, {
          method: "POST",
          kind: "first check",
        });
      } catch (_error) {
        queued = false;
      }
      await renderRoute({ focus: true });
      showToast(queued ? "Competitor URL added. First check queued." : "Competitor URL added. Queue unavailable.", queued ? "" : "error");
    } catch (error) {
      setFormBusy(form, false);
      showToast(safeActionMessage(error, "Competitor URL"), "error");
    }
  }

  async function submitCompetitor(form) {
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const adapterSelect = form.querySelector("#competitor-adapter");
    const selected = adapterSelect.selectedOptions[0];
    const currency = String(data.get("expected_currency") || "").trim().toUpperCase();
    const payload = {
      name: String(data.get("name") || "").trim(),
      base_url: String(data.get("base_url") || "").trim(),
      adapter_key: String(data.get("adapter_key") || ""),
      fetch_mode: selected.dataset.fetchMode,
    };
    if (currency) payload.expected_currency = currency;
    setFormBusy(form, true, "Adding");
    try {
      await request(`/customers/${selectedCustomerId()}/competitors`, {
        method: "POST",
        body: payload,
        kind: "competitor",
      });
      await renderRoute({ focus: true });
      showToast("Competitor added.");
    } catch (error) {
      setFormBusy(form, false);
      showToast(safeActionMessage(error, "Competitor"), "error");
    }
  }

  async function submitAlert(form) {
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const payload = {
      product_id: safeId(data.get("product_id")),
      direction: String(data.get("direction") || "either"),
      threshold_percent: String(data.get("threshold_percent") || ""),
    };
    setFormBusy(form, true, "Creating");
    try {
      await request(`/customers/${selectedCustomerId()}/alert-rules`, {
        method: "POST",
        body: payload,
        kind: "alert",
      });
      await renderRoute({ focus: true });
      showToast("Alert created.");
    } catch (error) {
      setFormBusy(form, false);
      showToast(safeActionMessage(error, "Alert"), "error");
    }
  }

  async function checkNow(button) {
    const targetId = safeId(button.dataset.targetId);
    if (!targetId) return;
    button.disabled = true;
    const idle = button.textContent;
    button.textContent = "Queueing";
    try {
      const result = await request(`/competitor-products/${targetId}/scrapes`, {
        method: "POST",
        kind: "check",
      });
      await renderRoute({ focus: true });
      showToast(result.status === "running" ? "Check already running." : "Check queued.");
    } catch (error) {
      button.disabled = false;
      button.textContent = idle;
      showToast(safeActionMessage(error, "Check"), "error");
    }
  }

  async function toggleAlert(button) {
    const alertId = safeId(button.dataset.alertId);
    if (!alertId) return;
    const isActive = button.dataset.alertActive === "true";
    button.disabled = true;
    try {
      await request(`/alert-rules/${alertId}`, {
        method: "PATCH",
        body: { is_active: !isActive },
        kind: "alert",
      });
      await renderRoute({ focus: true });
      showToast(isActive ? "Alert paused." : "Alert resumed.");
    } catch (error) {
      button.disabled = false;
      showToast(safeActionMessage(error, "Alert"), "error");
    }
  }

  async function deleteAlert(button) {
    const alertId = safeId(button.dataset.alertId);
    if (!alertId) return;
    if (!window.confirm("Remove this alert rule?")) return;
    button.disabled = true;
    try {
      await request(`/alert-rules/${alertId}`, {
        method: "DELETE",
        kind: "alert",
      });
      await renderRoute({ focus: true });
      showToast("Alert removed.");
    } catch (error) {
      button.disabled = false;
      showToast(safeActionMessage(error, "Alert"), "error");
    }
  }

  function slugify(value) {
    return String(value)
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 100);
  }

  document.addEventListener("click", async (event) => {
    const navLink = event.target.closest("a[data-nav]");
    if (navLink && !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
      const url = new URL(navLink.href, window.location.origin);
      if (url.origin === window.location.origin) {
        event.preventDefault();
        await navigate(url.href);
        return;
      }
    }

    const action = event.target.closest("[data-action]");
    if (action) {
      if (action.dataset.action === "retry") await renderRoute({ focus: true });
      else if (action.dataset.action === "product-filter") {
        state.productFilter = action.dataset.filter;
        document.querySelectorAll('[data-action="product-filter"]').forEach((button) => {
          button.setAttribute("aria-pressed", String(button === action));
        });
        applyProductFilters(safeId(new URLSearchParams(window.location.search).get("competitor")));
      } else if (action.dataset.action === "competitor-filter") {
        state.competitorFilter = action.dataset.filter;
        document.querySelectorAll('[data-action="competitor-filter"]').forEach((button) => {
          button.setAttribute("aria-pressed", String(button === action));
        });
        applyCompetitorFilters();
      } else if (action.dataset.action === "check-now") await checkNow(action);
      else if (action.dataset.action === "toggle-alert") await toggleAlert(action);
      else if (action.dataset.action === "delete-alert") await deleteAlert(action);
      return;
    }

    const row = event.target.closest("tr[data-href]");
    if (row && !event.target.closest("a, button, input, select")) {
      await navigate(row.dataset.href);
    }
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    event.preventDefault();
    if (form.id === "session-form") await submitSession(form);
    else if (form.id === "workspace-form") await submitWorkspace(form);
    else if (form.id === "product-form") await submitProduct(form);
    else if (form.id === "add-offer-form") await submitOffer(form);
    else if (form.id === "competitor-form") await submitCompetitor(form);
    else if (form.id === "alert-form") await submitAlert(form);
  });

  document.addEventListener("input", (event) => {
    if (event.target.id === "product-search") {
      state.search = event.target.value;
      applyProductFilters(safeId(new URLSearchParams(window.location.search).get("competitor")));
    }
    if (event.target.id === "workspace-name") {
      const slug = document.querySelector("#workspace-slug");
      if (slug && !slug.dataset.edited) slug.value = slugify(event.target.value);
    }
    if (event.target.id === "workspace-slug") event.target.dataset.edited = "true";
    if (["own-currency", "competitor-currency", "workspace-currency"].includes(event.target.id)) {
      const start = event.target.selectionStart;
      event.target.value = event.target.value.toUpperCase();
      event.target.setSelectionRange(start, start);
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.id === "competitor-adapter") {
      const option = event.target.selectedOptions[0];
      const help = document.querySelector("#adapter-hosts");
      if (help) help.textContent = `Allowed: ${option.dataset.hosts}`;
    }
  });

  workspaceSelect.addEventListener("change", async () => {
    const customerId = safeId(workspaceSelect.value);
    if (!customerId) return;
    await navigate(`/?customer=${encodeURIComponent(customerId)}`);
  });

  sessionLogout.addEventListener("click", async () => {
    sessionLogout.disabled = true;
    try {
      state.session = await sessionRequest("DELETE");
      renderAccess();
    } catch (_error) {
      showToast("Could not sign out.", "error");
      sessionLogout.disabled = false;
    }
  });

  window.addEventListener("popstate", () => renderRoute({ focus: true }));
  checkService();
  renderRoute();
})();
