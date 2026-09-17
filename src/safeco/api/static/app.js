// SafeCO operator console client.
//
// Polls the local API and renders plant state, alerts, events, scenario
// controls, and system health across sidebar-navigated views. SafeCO is
// advisory: this page only reads state and records acknowledgement. It never
// issues or blocks a control command.
//
// Offline story: if the local control feed cannot be reached, the page keeps the
// last-known values on screen and shows a degraded-visibility banner rather than
// blanking out or implying the plant is fine.

"use strict";

// Poll cadence in milliseconds. The console re-fetches the feed this often, and
// also refreshes immediately after an operator action (acknowledge, run,
// filter, manual refresh) so those changes are not gated by the interval.
const POLL_MS = 2000;

const DEFAULT_SITE_NAME = "Adupe Municipal Water Station";

// Fetch a generous window so the operator can page through recent history
// client-side; the API caps limit at 500.
const LIST_LIMIT = 500;

const API = {
  health: "/api/health",
  plant: "/api/plant/state",
  events: `/api/events?limit=${LIST_LIMIT}`,
  alerts: `/api/alerts?limit=${LIST_LIMIT}`,
  scenarios: "/api/scenarios",
};

// Per-view pagination state. pageSize is a number, or "all" to show everything.
const paging = {
  alerts: { page: 1, pageSize: 10 },
  events: { page: 1, pageSize: 20 },
};

const state = {
  lastGood: null,
  alertFilter: "all",
  alertSearch: "",
  eventScenario: "",
  lastUpdated: null,
};

/**
 * Return the slice of `items` for the current page of a paginated view, and
 * update that view's page-status label and prev/next disabled state.
 *
 * Keeps the requested page within range (so deletions or filters never strand
 * the operator on an empty page) and treats a pageSize of "all" as one page.
 */
function paginate(view, items) {
  const cfg = paging[view];
  const total = items.length;
  const sizeAll = cfg.pageSize === "all";
  const size = sizeAll ? Math.max(total, 1) : cfg.pageSize;
  const pageCount = Math.max(1, Math.ceil(total / size));
  if (cfg.page > pageCount) cfg.page = pageCount;
  if (cfg.page < 1) cfg.page = 1;
  const startIndex = (cfg.page - 1) * size;
  const shown = items.slice(startIndex, startIndex + size);

  const pager = document.querySelector(`[data-pager="${view}"]`);
  if (pager) {
    pager.hidden = total === 0;
    const statusEl = pager.querySelector(`[data-page-status="${view}"]`);
    if (total === 0) {
      statusEl.textContent = "0 of 0";
    } else {
      const first = startIndex + 1;
      const last = startIndex + shown.length;
      statusEl.textContent =
        `${first}–${last} of ${total}` +
        (sizeAll ? "" : ` · page ${cfg.page}/${pageCount}`);
    }
    pager.querySelector(`[data-page-prev="${view}"]`).disabled =
      sizeAll || cfg.page <= 1;
    pager.querySelector(`[data-page-next="${view}"]`).disabled =
      sizeAll || cfg.page >= pageCount;
  }
  return shown;
}

/** Wire the page-size selector and prev/next buttons for one paginated view. */
function setupPager(view, rerender) {
  const size = document.querySelector(`[data-page-size="${view}"]`);
  if (size) {
    size.addEventListener("change", () => {
      const value = size.value;
      paging[view].pageSize = value === "all" ? "all" : Number(value);
      paging[view].page = 1;
      rerender();
    });
  }
  const prev = document.querySelector(`[data-page-prev="${view}"]`);
  if (prev) {
    prev.addEventListener("click", () => {
      paging[view].page -= 1;
      rerender();
    });
  }
  const next = document.querySelector(`[data-page-next="${view}"]`);
  if (next) {
    next.addEventListener("click", () => {
      paging[view].page += 1;
      rerender();
    });
  }
}

async function getJSON(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} -> ${response.status}`);
  return response.json();
}

/* ---------- Sidebar navigation ---------- */

function activateTab(name) {
  for (const tab of document.querySelectorAll("[data-tab]")) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  for (const panel of document.querySelectorAll("[data-panel]")) {
    panel.hidden = panel.dataset.panel !== name;
  }
}

function setupTabs() {
  for (const tab of document.querySelectorAll("[data-tab]")) {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  }
  activateTab("plant");
}

/* ---------- Fixed demo-site identity ---------- */

function setupSiteName() {
  const site = document.getElementById("site-name");
  site.textContent = DEFAULT_SITE_NAME;
  document.title = `SafeCO — ${DEFAULT_SITE_NAME}`;
}

/* ---------- Live status ---------- */

function setLive(mode, message) {
  const dot = document.getElementById("live-dot");
  const text = document.getElementById("live-text");
  dot.className = `live-dot ${mode}`;
  text.textContent = message;
}

function setBanner(mode, message) {
  const banner = document.getElementById("health-banner");
  banner.hidden = false;
  banner.className = `banner ${mode}`;
  banner.textContent = message;
}

/* ---------- Plant state ---------- */

function fmtPercent(value) {
  return value === null || value === undefined ? "—" : `${Number(value).toFixed(1)}%`;
}

function pillClass(field, value) {
  const v = String(value).toLowerCase();
  if (field === "power_source") {
    if (v === "off" || v === "unknown") return "bad";
    if (v === "generator") return "info";
    return "good";
  }
  if (field === "mode") return v === "recovery" ? "warn" : "info";
  if (field === "pump_state") return v === "on" ? "info" : "";
  if (field === "inlet_valve_state" || field === "outlet_valve_state") {
    return v === "open" ? "good" : "";
  }
  return "";
}

function setPill(root, field, value) {
  const holder = root.querySelector(`[data-field="${field}"]`);
  if (!holder) return;
  const pill = holder.querySelector(".pill");
  if (pill) {
    pill.textContent = value ?? "—";
    pill.className = `pill ${pillClass(field, value)}`.trim();
  } else {
    holder.textContent = value ?? "—";
  }
}

function renderPlant(payload) {
  const panel = document.getElementById("plant-state");
  const empty = panel.querySelector("[data-empty]");
  const body = panel.querySelector(".plant-body");

  if (!payload || payload.status === "no_data" || !payload.process) {
    empty.hidden = false;
    body.hidden = true;
    return;
  }
  const p = payload.process;
  empty.hidden = true;
  body.hidden = false;

  setPill(body, "mode", p.mode);
  setPill(body, "power_source", p.power_source);
  setPill(body, "pump_state", p.pump_state);
  setPill(body, "inlet_valve_state", p.inlet_valve_state);
  setPill(body, "outlet_valve_state", p.outlet_valve_state);
  const targetEl = body.querySelector('[data-field="target_level"]');
  if (targetEl) targetEl.textContent = fmtPercent(p.target_level);
  const limitEl = body.querySelector('[data-field="high_level_limit"]');
  if (limitEl) limitEl.textContent = fmtPercent(p.high_level_limit);

  const tankLabelEl = body.querySelector('[data-field="tank_level"]');
  if (tankLabelEl) tankLabelEl.textContent = fmtPercent(p.tank_level);
  const level = Math.max(0, Math.min(100, Number(p.tank_level) || 0));
  const svg = body.querySelector(".tank-svg");
  const waterRect = body.querySelector('[data-field="tank_water"]');
  const waveBack = body.querySelector('[data-field="tank_wave_back"]');
  const waveMid = body.querySelector('[data-field="tank_wave_mid"]');
  const waveFront = body.querySelector('[data-field="tank_wave_front"]');
  const pctText = body.querySelector('[data-field="tank_pct"]');

  if (waterRect && pctText) {
    // Water fill: top of water = 320 - (level/100 * 320)
    const waterTop = 320 - (level / 100) * 320;
    const waterH = 320 - waterTop;
    waterRect.setAttribute("y", waterTop);
    waterRect.setAttribute("height", waterH);
    // Position wave groups at the water surface (y-attr, not transform)
    if (waveBack) waveBack.setAttribute("y", waterTop);
    if (waveMid) waveMid.setAttribute("y", waterTop);
    if (waveFront) waveFront.setAttribute("y", waterTop);
    pctText.textContent = `${level.toFixed(1)}%`;
    // Position pct text: above water if enough room, otherwise centered
    const textY = level > 12 ? waterTop - 18 : 160;
    pctText.setAttribute("y", Math.max(30, textY));
  }

  // Animate waves when feed is live
  const liveDot = document.getElementById("live-dot");
  if (svg && liveDot) {
    const shouldAnimate = liveDot.classList.contains("ok");
    svg.classList.toggle("animate", shouldAnimate);
  }

  // Status card — matches the plant detector: only two states exist.
  // Critical: level >= high_level_limit  (real detector rule)
  // Normal:   level < high_level_limit
  const limit = p.high_level_limit;
  const target = p.target_level;
  const over = limit !== null && limit !== undefined && level >= Number(limit);
  const statusDot = body.querySelector('[data-field="tank_status_dot"]');
  const statusText = body.querySelector('[data-field="tank_status"]');
  const targetDisp = body.querySelector('[data-field="tank_target_display"]');
  const updatedDisp = body.querySelector('[data-field="tank_updated"]');
  if (statusDot && statusText) {
    if (over) {
      statusDot.className = "tank-status-dot crit";
      statusText.textContent = "Critical";
    } else {
      statusDot.className = "tank-status-dot ok";
      statusText.textContent = "Normal";
    }
  }
  if (targetDisp) {
    targetDisp.textContent = target !== null && target !== undefined
      ? fmtPercent(target)
      : "—";
  }
  if (updatedDisp) {
    const ts = payload.timestamp || "";
    updatedDisp.textContent = ts ? ts.split("T")[1]?.split("+")[0] || ts : "—";
  }

  // Side markers — only real plant thresholds, no fabricated values.
  // Positioned at their actual percentage height (bottom: {pct}%).
  const markers = body.querySelector('[data-field="tank_markers"]');
  if (markers) {
    const markerDefs = [];
    if (target !== null && target !== undefined) {
      markerDefs.push({ label: "Target", pct: Number(target), color: "var(--accent)" });
    }
    if (limit !== null && limit !== undefined) {
      markerDefs.push({ label: "Limit", pct: Number(limit), color: "var(--crit)" });
    }
    markerDefs.sort((a, b) => a.pct - b.pct);
    markers.innerHTML = markerDefs
      .map(
        (m) =>
          `<div class="tank-marker" style="bottom: ${m.pct}%"><span>${m.label} ${m.pct.toFixed(0)}%</span><span class="tank-marker-line" style="background:${m.color}"></span></div>`
      )
      .join("");
  }
}

/* ---------- Events ---------- */

function formatValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderEvents(rows) {
  const panel = document.getElementById("events");
  const empty = panel.querySelector("[data-empty]");
  const wrap = panel.querySelector(".table-wrap");
  const body = wrap.querySelector("tbody");
  body.textContent = "";

  const all = rows || [];
  if (all.length === 0) {
    empty.hidden = false;
    wrap.hidden = true;
    paginate("events", all);
    return;
  }
  empty.hidden = true;
  wrap.hidden = false;
  const shown = paginate("events", all);
  for (const ev of shown) {
    const tr = document.createElement("tr");
    const time = document.createElement("td");
    time.textContent = (ev.timestamp || "").replace("T", " ").slice(0, 19);
    const scenario = document.createElement("td");
    scenario.textContent = ev.scenario_id ?? "";
    const gt = document.createElement("td");
    const gtSpan = document.createElement("span");
    gtSpan.className = `gt gt-${ev.ground_truth}`;
    gtSpan.textContent = ev.ground_truth ?? "";
    gt.appendChild(gtSpan);
    tr.append(time, scenario, gt);
    for (const value of [ev.source, ev.command, ev.target, formatValue(ev.value), ev.mode]) {
      const td = document.createElement("td");
      td.textContent = value ?? "";
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

/* ---------- Alerts ---------- */

function updateAlertBadge(alerts) {
  const badge = document.querySelector("[data-alert-count]");
  const pending = alerts.filter((a) => a.acknowledged === false).length;
  badge.textContent = String(pending);
  badge.hidden = pending === 0;
}

function filterAlerts(alerts) {
  let shown = alerts;
  if (state.alertFilter === "unacknowledged") {
    shown = shown.filter((a) => a.acknowledged === false);
  } else if (state.alertFilter === "acknowledged") {
    shown = shown.filter((a) => a.acknowledged === true);
  }
  const q = state.alertSearch.trim().toLowerCase();
  if (q) shown = shown.filter((a) => String(a.alert_id).toLowerCase().includes(q));
  return shown;
}

function renderAlerts(alerts) {
  const panel = document.getElementById("alerts");
  const empty = panel.querySelector("[data-empty]");
  const list = panel.querySelector(".alert-list");
  list.textContent = "";

  const matched = filterAlerts(alerts);
  if (!matched || matched.length === 0) {
    empty.hidden = false;
    empty.textContent =
      state.alertSearch || state.alertFilter !== "all"
        ? "No alerts match the current filter."
        : "No alerts. An empty queue is not proof of safety.";
    paginate("alerts", matched || []);
    return;
  }
  empty.hidden = true;
  const shown = paginate("alerts", matched);
  for (const alert of shown) list.appendChild(renderAlert(alert));
}

function renderAlert(alert) {
  const sev = `sev-${alert.severity}`;
  const li = document.createElement("li");
  li.className = `alert ${sev}${alert.acknowledged ? " acknowledged" : ""}`;

  const head = document.createElement("div");
  head.className = "alert-head";
  const title = document.createElement("span");
  title.className = "alert-title";
  title.textContent = alert.title;
  const right = document.createElement("span");
  if (alert.acknowledged) {
    const flag = document.createElement("span");
    flag.className = "ack-flag";
    flag.textContent = "✓ acknowledged";
    right.appendChild(flag);
  } else {
    const tag = document.createElement("span");
    tag.className = `sev-tag ${sev}`;
    tag.textContent = alert.severity;
    right.appendChild(tag);
  }
  head.append(title, right);
  li.appendChild(head);

  // Alert id, exposed with a copy button so an operator can search for it.
  const idRow = document.createElement("div");
  idRow.className = "alert-id";
  const idLabel = document.createElement("span");
  idLabel.textContent = "Alert ID";
  const idCode = document.createElement("code");
  idCode.textContent = alert.alert_id;
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "copy-btn";
  copyBtn.textContent = "Copy";
  copyBtn.addEventListener("click", () => copyAlertId(alert.alert_id, copyBtn));
  idRow.append(idLabel, idCode, copyBtn);
  li.appendChild(idRow);

  const dl = document.createElement("dl");
  appendRow(dl, "Why it matters", alert.explanation);
  appendRow(dl, "Recommended action", alert.recommended_action);
  appendConfidence(dl, alert.confidence);
  appendRow(dl, "Event", alert.event_id);
  appendEvidence(dl, alert.evidence);
  li.appendChild(dl);

  if (!alert.acknowledged) {
    const actions = document.createElement("div");
    actions.className = "alert-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Acknowledge (record only)";
    button.title = "Records that an engineer has seen this. Does not change the plant.";
    button.addEventListener("click", () => acknowledge(alert.alert_id, button));
    actions.appendChild(button);
    li.appendChild(actions);
  }
  return li;
}

function appendRow(dl, label, value) {
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value ?? "";
  dl.append(dt, dd);
}

function appendEvidence(dl, evidence) {
  const dt = document.createElement("dt");
  dt.textContent = "Evidence";
  const dd = document.createElement("dd");
  dd.className = "evidence";
  dd.textContent = JSON.stringify(evidence ?? {}, null, 0);
  dl.append(dt, dd);
}

function appendConfidence(dl, confidence) {
  const pct = Math.round((confidence ?? 0) * 100);
  const dt = document.createElement("dt");
  dt.textContent = "Confidence";
  const dd = document.createElement("dd");
  const meter = document.createElement("span");
  meter.className = "confidence-meter";
  const fill = document.createElement("span");
  fill.className = "confidence-fill";
  fill.style.display = "block";
  fill.style.width = `${pct}%`;
  fill.style.height = "100%";
  meter.appendChild(fill);
  dd.append(meter, document.createTextNode(`${pct}%`));
  dl.append(dt, dd);
}

async function copyAlertId(alertId, button) {
  try {
    await navigator.clipboard.writeText(alertId);
    const original = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => {
      button.textContent = original;
    }, 1200);
  } catch (err) {
    button.textContent = "Copy failed";
  }
}

async function acknowledge(alertId, button) {
  button.disabled = true;
  try {
    const response = await fetch(`/api/alerts/${encodeURIComponent(alertId)}/ack`, {
      method: "PATCH",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`ack -> ${response.status}`);
    await refresh();
  } catch (err) {
    button.disabled = false;
    button.textContent = "Acknowledge failed — retry";
  }
}

function setupAlertControls() {
  for (const chip of document.querySelectorAll("[data-filter]")) {
    chip.addEventListener("click", () => {
      state.alertFilter = chip.dataset.filter;
      paging.alerts.page = 1;
      for (const c of document.querySelectorAll("[data-filter]")) {
        c.classList.toggle("active", c === chip);
      }
      if (state.lastGood) renderAlerts(state.lastGood.alerts);
    });
  }
  const search = document.getElementById("alert-search");
  search.addEventListener("input", () => {
    state.alertSearch = search.value;
    paging.alerts.page = 1;
    if (state.lastGood) renderAlerts(state.lastGood.alerts);
  });
}

/** Re-render one paginated view from the last good payload. */
function rerenderAlerts() {
  if (state.lastGood) renderAlerts(state.lastGood.alerts);
}

function rerenderEvents() {
  if (state.lastGood) renderEvents(state.lastGood.events);
}

/* ---------- Health view ---------- */

function renderHealth(health) {
  const page = document.getElementById("health-page");
  const setHealthPill = (key, value, cls) => {
    const holder = page.querySelector(`[data-health="${key}"]`);
    const pill = holder.querySelector(".pill");
    if (pill) {
      pill.textContent = value;
      pill.className = `pill ${cls}`.trim();
    } else {
      holder.textContent = value;
    }
  };
  const degraded = health.degraded_visibility;
  setHealthPill("status", health.status, degraded ? "bad" : "good");
  setHealthPill("visibility", degraded ? "degraded" : "full", degraded ? "bad" : "good");
  setHealthPill("database", health.database, "info");
  page.querySelector('[data-health="event_count"]').textContent = String(
    health.event_count ?? 0
  );
  page.querySelector('[data-health="last_event"]').textContent =
    health.last_event_timestamp || "— none yet —";
}

/* ---------- Scenarios ---------- */

async function loadScenarios() {
  const select = document.getElementById("scenario-select");
  const eventFilter = document.getElementById("event-scenario-filter");
  try {
    const ids = await getJSON(API.scenarios);
    select.textContent = "";
    eventFilter.textContent = "";
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "All scenarios";
    eventFilter.appendChild(allOption);
    for (const id of ids) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = id;
      select.appendChild(option);

      const filterOption = document.createElement("option");
      filterOption.value = id;
      filterOption.textContent = id;
      eventFilter.appendChild(filterOption);
    }
  } catch (err) {
    /* Non-fatal: scenario controls stay empty if discovery fails. */
  }
}

async function runScenario(event) {
  event.preventDefault();
  const scenario = document.getElementById("scenario-select").value;
  const seed = document.getElementById("seed-input").value || "42";
  const result = document.getElementById("scenario-result");
  if (!scenario) return;
  result.textContent = `Running ${scenario} (seed ${seed})…`;
  try {
    const url = `/api/scenarios/${encodeURIComponent(scenario)}/run?seed=${encodeURIComponent(seed)}`;
    const response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`run -> ${response.status}`);
    const data = await response.json();
    const violations = (data.violations || []).length;
    result.textContent =
      `${data.scenario_id}: ${data.events} events, ${data.alerts} alert(s), ` +
      `${violations} invariant violation(s), ground truth "${data.ground_truth}".`;
    await refresh();
  } catch (err) {
    result.textContent = `Could not run scenario: ${err.message}`;
  }
}

/* ---------- Event scenario filter ---------- */

function setupEventFilter() {
  const select = document.getElementById("event-scenario-filter");
  select.addEventListener("change", () => {
    state.eventScenario = select.value;
    paging.events.page = 1;
    refresh();
  });
}

function eventsUrl() {
  return state.eventScenario
    ? `/api/events?limit=${LIST_LIMIT}&scenario_id=${encodeURIComponent(state.eventScenario)}`
    : API.events;
}

/* ---------- Poll loop ---------- */

async function refresh() {
  const btn = document.getElementById("refresh-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing…";
  }
  try {
    const [health, plant, events, alerts] = await Promise.all([
      getJSON(API.health),
      getJSON(API.plant),
      getJSON(eventsUrl()),
      getJSON(API.alerts),
    ]);
    state.lastGood = { health, plant, events, alerts };
    state.lastUpdated = Date.now();

    if (health.degraded_visibility) {
      const detail = health.event_count
        ? "no fresh events — the local feed may be down. Showing last-known values."
        : "no events recorded yet. Run a scenario or start the feed.";
      setBanner("degraded", `Degraded visibility — ${detail}`);
      setLive("degraded", "feed degraded");
    } else {
      setBanner("ok", `Local feed healthy. Last event ${health.last_event_timestamp}.`);
      setLive("ok", "feed healthy · just now");
    }
    renderPlant(plant);
    renderEvents(events);
    renderAlerts(alerts);
    updateAlertBadge(alerts);
    renderHealth(health);
  } catch (err) {
    setLive("degraded", "feed unreachable");
    markDegradedBanner(err.message);
    if (state.lastGood) {
      renderPlant(state.lastGood.plant);
      renderEvents(state.lastGood.events);
      renderAlerts(state.lastGood.alerts);
      updateAlertBadge(state.lastGood.alerts);
      renderHealth(state.lastGood.health);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Refresh";
    }
  }
}

function markDegradedBanner(reason) {
  setBanner(
    "degraded",
    `Degraded visibility — the local control feed is unreachable (${reason}). ` +
      "Showing last-known values. SafeCO cannot see commands while the feed is down."
  );
}

function tickLiveClock() {
  if (!state.lastUpdated) return;
  const dot = document.getElementById("live-dot");
  if (dot.classList.contains("degraded")) return;
  const secs = Math.round((Date.now() - state.lastUpdated) / 1000);
  const when = secs <= 1 ? "just now" : `${secs}s ago`;
  document.getElementById("live-text").textContent = `feed healthy · updated ${when}`;
}

function start() {
  setupTabs();
  setupSiteName();
  setupAlertControls();
  setupEventFilter();
  setupPager("alerts", rerenderAlerts);
  setupPager("events", rerenderEvents);
  document.getElementById("scenario-form").addEventListener("submit", runScenario);
  document.getElementById("refresh-btn").addEventListener("click", refresh);
  loadScenarios();
  refresh();
  setInterval(refresh, POLL_MS);
  setInterval(tickLiveClock, 1000);
}

document.addEventListener("DOMContentLoaded", start);
