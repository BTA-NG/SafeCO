// SafeCO operator dashboard client.
//
// Polls the local API and renders plant state, recent events, and alerts.
// SafeCO is advisory: this page only reads state and records acknowledgement.
// It never issues or blocks a control command.
//
// Offline story: if the local control feed cannot be reached, the page keeps
// the last-known values on screen and shows a degraded-visibility banner rather
// than blanking out or implying the plant is fine.

"use strict";

const POLL_MS = 3000;

const API = {
  health: "/api/health",
  plant: "/api/plant/state",
  events: "/api/events?limit=25",
  alerts: "/api/alerts",
  scenarios: "/api/scenarios",
};

const state = { lastGood: null, degraded: false };

async function getJSON(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${url} -> ${response.status}`);
  }
  return response.json();
}

function setBanner(mode, message) {
  const banner = document.getElementById("health-banner");
  banner.hidden = false;
  banner.className = `banner ${mode}`;
  banner.textContent = message;
}

function markDegraded(reason) {
  state.degraded = true;
  setBanner(
    "degraded",
    `Degraded visibility — the local control feed is unreachable (${reason}). ` +
      "Showing last-known values. SafeCO cannot see commands while the feed is down."
  );
}

function fmtPercent(value) {
  return value === null || value === undefined ? "—" : `${Number(value).toFixed(1)}%`;
}

function renderPlant(payload) {
  const panel = document.getElementById("plant-state");
  const empty = panel.querySelector("[data-empty]");
  const grid = panel.querySelector(".state-grid");
  const track = panel.querySelector(".level-track");

  if (!payload || payload.status === "no_data" || !payload.process) {
    empty.hidden = false;
    grid.hidden = true;
    track.hidden = true;
    return;
  }
  const p = payload.process;
  empty.hidden = true;
  grid.hidden = false;
  track.hidden = false;

  const set = (field, value) => {
    const node = grid.querySelector(`[data-field="${field}"]`);
    if (node) node.textContent = value;
  };
  set("mode", p.mode ?? "—");
  set("tank_level", fmtPercent(p.tank_level));
  set("pump_state", p.pump_state ?? "—");
  set("inlet_valve_state", p.inlet_valve_state ?? "—");
  set("outlet_valve_state", p.outlet_valve_state ?? "—");
  set("power_source", p.power_source ?? "—");
  set("target_level", fmtPercent(p.target_level));
  set("high_level_limit", fmtPercent(p.high_level_limit));

  const level = Math.max(0, Math.min(100, Number(p.tank_level) || 0));
  track.querySelector(".level-fill").style.width = `${level}%`;
  const limitMark = track.querySelector(".level-limit");
  if (p.high_level_limit === null || p.high_level_limit === undefined) {
    limitMark.hidden = true;
  } else {
    limitMark.hidden = false;
    limitMark.style.left = `${Math.max(0, Math.min(100, p.high_level_limit))}%`;
  }
}

function renderEvents(rows) {
  const panel = document.getElementById("events");
  const empty = panel.querySelector("[data-empty]");
  const table = panel.querySelector(".events-table");
  const body = table.querySelector("tbody");
  body.textContent = "";

  if (!rows || rows.length === 0) {
    empty.hidden = false;
    table.hidden = true;
    return;
  }
  empty.hidden = true;
  table.hidden = false;
  for (const ev of rows) {
    const tr = document.createElement("tr");
    const cells = [
      (ev.timestamp || "").replace("T", " ").slice(0, 19),
      ev.scenario_id,
      ev.source,
      ev.command,
      ev.target,
      formatValue(ev.value),
      ev.mode,
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value ?? "";
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

function formatValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderAlerts(alerts) {
  const panel = document.getElementById("alerts");
  const empty = panel.querySelector("[data-empty]");
  const list = panel.querySelector(".alert-list");
  list.textContent = "";

  if (!alerts || alerts.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  for (const alert of alerts) {
    list.appendChild(renderAlert(alert));
  }
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
  const tag = document.createElement("span");
  tag.className = `sev-tag ${sev}`;
  tag.textContent = alert.severity;
  head.append(title, tag);
  li.appendChild(head);

  const dl = document.createElement("dl");
  const rows = [
    ["Why it matters", alert.explanation],
    ["Recommended action", alert.recommended_action],
    ["Confidence", `${Math.round((alert.confidence ?? 0) * 100)}%`],
    ["Event", alert.event_id],
    ["Evidence", JSON.stringify(alert.evidence, null, 0)],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (label === "Evidence") dd.className = "evidence";
    dd.textContent = value ?? "";
    dl.append(dt, dd);
  }
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

async function loadScenarios() {
  const select = document.getElementById("scenario-select");
  try {
    const ids = await getJSON(API.scenarios);
    select.textContent = "";
    for (const id of ids) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = id;
      select.appendChild(option);
    }
  } catch (err) {
    // Non-fatal: scenario controls just stay empty if discovery fails.
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
    result.textContent =
      `${data.scenario_id}: ${data.events} events, ${data.alerts} alert(s), ` +
      `ground truth "${data.ground_truth}".`;
    await refresh();
  } catch (err) {
    result.textContent = `Could not run scenario: ${err.message}`;
  }
}

async function refresh() {
  try {
    const [health, plant, events, alerts] = await Promise.all([
      getJSON(API.health),
      getJSON(API.plant),
      getJSON(API.events),
      getJSON(API.alerts),
    ]);
    state.lastGood = { health, plant, events, alerts };
    state.degraded = false;

    if (health.degraded_visibility) {
      setBanner(
        "degraded",
        "Degraded visibility — no events recorded yet. Run a scenario or start the feed."
      );
    } else {
      setBanner("ok", `Local feed healthy. Last event ${health.last_event_timestamp}.`);
    }
    renderPlant(plant);
    renderEvents(events);
    renderAlerts(alerts);
  } catch (err) {
    // Keep last-known values on screen; surface the degraded state.
    markDegraded(err.message);
    if (state.lastGood) {
      renderPlant(state.lastGood.plant);
      renderEvents(state.lastGood.events);
      renderAlerts(state.lastGood.alerts);
    }
  }
}

function start() {
  document.getElementById("scenario-form").addEventListener("submit", runScenario);
  loadScenarios();
  refresh();
  setInterval(refresh, POLL_MS);
}

document.addEventListener("DOMContentLoaded", start);
