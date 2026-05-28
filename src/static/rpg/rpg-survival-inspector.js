(function () {
  "use strict";

  const STYLE_ID = "rpg-survival-inspector-css";
  const PANEL_ID = "rpg-survival-inspector-panel";
  const SOURCE = "rpg_survival_inspector";

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function safeArr(value) {
    return Array.isArray(value) ? value : [];
  }

  function safeStr(value) {
    return value == null ? "" : String(value);
  }

  function safeNum(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? n : (fallback || 0);
  }

  function escapeHtml(value) {
    return safeStr(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function clampPct(value) {
    return Math.max(0, Math.min(100, Math.round(safeNum(value, 0))));
  }

  function resultRoot(payload) {
    payload = safeObj(payload);
    return safeObj(payload.result || payload);
  }

  function turnContractRoot(payload) {
    payload = safeObj(payload);
    return safeObj(payload.turn_contract || safeObj(payload.result).turn_contract || payload);
  }

  function simulationRoot(payload) {
    payload = safeObj(payload);
    return safeObj(
      payload.simulation_state ||
      safeObj(payload.session).simulation_state ||
      safeObj(safeObj(payload.result).session).simulation_state
    );
  }

  function firstObj() {
    for (let i = 0; i < arguments.length; i += 1) {
      const candidate = safeObj(arguments[i]);
      if (Object.keys(candidate).length) return candidate;
    }
    return {};
  }

  function survivalState(payload) {
    const result = resultRoot(payload);
    const contract = turnContractRoot(payload);
    const sim = simulationRoot(payload);
    const actionContext = safeObj(result.survival_action_context || contract.survival_action_context);
    return firstObj(
      result.survival,
      contract.survival,
      actionContext.survival,
      sim.survival
    );
  }

  function survivalPressure(payload, survival) {
    const result = resultRoot(payload);
    const contract = turnContractRoot(payload);
    const pressure = firstObj(
      result.survival_pressure,
      contract.survival_pressure,
      safeObj(result.survival_action_context).survival_pressure,
      safeObj(contract.survival_action_context).survival_pressure
    );
    if (Object.keys(pressure).length) return pressure;
    survival = safeObj(survival);
    const out = {};
    ["hunger", "thirst", "fatigue"].forEach((key) => {
      const value = safeNum(survival[key], 0);
      out[key] = value >= 75 ? "critical" : value >= 50 ? "high" : value >= 25 ? "moderate" : "low";
    });
    return out;
  }

  function survivalActionContext(payload) {
    const result = resultRoot(payload);
    const contract = turnContractRoot(payload);
    return firstObj(result.survival_action_context, contract.survival_action_context);
  }

  function suggestedSurvivalActions(payload) {
    const result = resultRoot(payload);
    const contract = turnContractRoot(payload);
    const context = survivalActionContext(payload);
    const rows = [];
    [
      ...safeArr(context.suggested_actions),
      ...safeArr(context.next_actions),
      ...safeArr(result.suggested_actions),
      ...safeArr(result.next_actions),
      ...safeArr(contract.suggested_actions),
      ...safeArr(contract.next_actions),
    ].forEach((row) => {
      row = safeObj(row);
      const category = safeStr(row.action_type || row.category);
      const actionId = safeStr(row.action_id || row.id || row.action);
      const action = safeStr(row.action || row.command || row.label || row.action_id);
      if (category !== "survival" && actionId.indexOf("survival:") !== 0) return;
      if (!action) return;
      if (rows.some((existing) => safeStr(existing.action_id || existing.action) === actionId)) return;
      rows.push(row);
    });
    return rows.slice(0, 6);
  }

  function recentSurvivalEvents(payload) {
    const state = survivalState(payload);
    const result = resultRoot(payload);
    const contract = turnContractRoot(payload);
    const events = [
      ...safeArr(state.events),
      ...safeArr(result.survival_event ? [result.survival_event] : []),
      ...safeArr(contract.survival_event ? [contract.survival_event] : []),
      ...safeArr(result.survival_tick_result ? [result.survival_tick_result] : []),
      ...safeArr(contract.survival_tick_result ? [contract.survival_tick_result] : []),
    ];
    return events.filter(Boolean).slice(-8).reverse();
  }

  function latestTickResult(payload) {
    const result = resultRoot(payload);
    const contract = turnContractRoot(payload);
    return firstObj(result.survival_tick_result, contract.survival_tick_result);
  }

  function ensureStylesheet() {
    if (document.getElementById(STYLE_ID)) return;
    const link = document.createElement("link");
    link.id = STYLE_ID;
    link.rel = "stylesheet";
    link.href = "/static/rpg/rpg-survival-inspector.css";
    document.head.appendChild(link);
  }

  function findHost() {
    return (
      document.getElementById("rpg-inspector-shell") ||
      document.getElementById("rpgInspectorPanel") ||
      document.getElementById("rpg-inspector-panel") ||
      document.getElementById("rpg-top-panels") ||
      document.getElementById("rpg-side-panels") ||
      document.querySelector("[data-rpg-inspector]") ||
      document.body
    );
  }

  function ensurePanel() {
    ensureStylesheet();
    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;
    panel = document.createElement("section");
    panel.id = PANEL_ID;
    panel.className = "rpg-survival-inspector-panel rpg-inspector-section";
    findHost().appendChild(panel);
    return panel;
  }

  function pressureClass(label) {
    label = safeStr(label).toLowerCase();
    if (["critical", "high", "moderate", "low"].indexOf(label) >= 0) return label;
    return "low";
  }

  function renderNeed(name, value, pressure) {
    const pct = clampPct(value);
    const label = safeStr(pressure || "low");
    return `
      <div class="rpg-survival-need rpg-survival-need--${escapeHtml(pressureClass(label))}">
        <div class="rpg-survival-need-head">
          <span>${escapeHtml(name)}</span>
          <strong>${pct}</strong>
          <em>${escapeHtml(label)}</em>
        </div>
        <div class="rpg-survival-meter" aria-label="${escapeHtml(name)} ${pct}">
          <span style="width: ${pct}%"></span>
        </div>
      </div>
    `;
  }

  function actionCommand(row) {
    row = safeObj(row);
    return safeStr(row.command || row.action || row.label || row.action_id).replace(/^survival:/, "").replace(/_/g, " ");
  }

  function renderActions(actions) {
    if (!actions.length) {
      return '<div class="rpg-survival-empty">No survival action pressure right now.</div>';
    }
    return actions.map((row) => {
      const command = actionCommand(row);
      return `
        <button type="button" class="rpg-survival-action" data-rpg-survival-command="${escapeHtml(command)}">
          <span>${escapeHtml(command)}</span>
          <small>${escapeHtml(row.reason || row.need || row.pressure || "survival")}</small>
        </button>
      `;
    }).join("");
  }

  function eventLabel(event) {
    event = safeObj(event);
    const kind = safeStr(event.kind || event.reason || event.action || "event");
    const effects = safeObj(event.effects);
    const deltas = Object.keys(effects).map((key) => `${key} ${effects[key]}`).join(", ");
    const inventory = safeObj(event.inventory_delta);
    const inv = Object.keys(inventory).map((key) => `${key} ${inventory[key]}`).join(", ");
    return [kind, deltas, inv].filter(Boolean).join(" · ");
  }

  function renderEvents(events) {
    if (!events.length) return '<div class="rpg-survival-empty">No survival events recorded yet.</div>';
    return events.map((event) => `
      <div class="rpg-survival-event">
        <strong>${escapeHtml(eventLabel(event))}</strong>
        <code>${escapeHtml(event.source || event.tick || "runtime")}</code>
      </div>
    `).join("");
  }

  function submitSurvivalCommand(command) {
    command = safeStr(command).trim();
    if (!command) return;
    if (typeof window.rpgSendMessage === "function") {
      window.rpgSendMessage(command);
      return;
    }
    if (typeof window.sendRpgMessage === "function") {
      window.sendRpgMessage(command);
      return;
    }
    const input =
      document.getElementById("rpg-command-input") ||
      document.getElementById("message-input") ||
      document.querySelector("textarea, input[type='text']");
    if (input) {
      input.value = command;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    }
  }

  function bindActionButtons(panel) {
    panel.querySelectorAll("[data-rpg-survival-command]").forEach((button) => {
      button.addEventListener("click", () => submitSurvivalCommand(button.getAttribute("data-rpg-survival-command")));
    });
  }

  function render(payload) {
    payload = safeObj(payload);
    const survival = survivalState(payload);
    const pressure = survivalPressure(payload, survival);
    const actions = suggestedSurvivalActions(payload);
    const events = recentSurvivalEvents(payload);
    const tick = latestTickResult(payload);
    const panel = ensurePanel();
    const enabled = survival.enabled !== false;

    panel.innerHTML = `
      <div class="rpg-survival-header">
        <div>
          <h3>Survival</h3>
          <div class="rpg-survival-meta">${enabled ? "Runtime pressure" : "Disabled"}${tick.reason ? " · " + escapeHtml(tick.reason) : ""}</div>
        </div>
        <span class="rpg-survival-source">${escapeHtml(SOURCE)}</span>
      </div>
      <div class="rpg-survival-needs">
        ${renderNeed("Hunger", survival.hunger, pressure.hunger)}
        ${renderNeed("Thirst", survival.thirst, pressure.thirst)}
        ${renderNeed("Fatigue", survival.fatigue, pressure.fatigue)}
      </div>
      <details class="rpg-survival-details" open>
        <summary>Suggested survival actions (${actions.length})</summary>
        <div class="rpg-survival-actions">${renderActions(actions)}</div>
      </details>
      <details class="rpg-survival-details">
        <summary>Recent survival events (${events.length})</summary>
        <div class="rpg-survival-events">${renderEvents(events)}</div>
      </details>
    `;
    bindActionButtons(panel);
    panel.dataset.hasSurvival = Object.keys(survival).length ? "true" : "false";
    window.__rpg_last_survival_payload = payload;
  }

  function maybeRenderPayload(payload) {
    payload = safeObj(payload);
    const survival = survivalState(payload);
    const context = survivalActionContext(payload);
    if (!Object.keys(survival).length && !Object.keys(context).length) return;
    render(payload);
  }

  function installFetchObserver() {
    if (window.__rpg_survival_fetch_observer_installed) return;
    if (typeof window.fetch !== "function") return;
    window.__rpg_survival_fetch_observer_installed = true;
    const originalFetch = window.fetch.bind(window);
    window.fetch = function () {
      const args = arguments;
      return originalFetch.apply(null, args).then((response) => {
        try {
          const url = safeStr(args[0] && (args[0].url || args[0]));
          if (url.indexOf("/api/rpg") >= 0 && response && response.clone) {
            response.clone().json().then(maybeRenderPayload).catch(() => {});
          }
        } catch (_) {}
        return response;
      });
    };
  }

  window.RpgSurvivalInspector = {
    render,
    maybeRenderPayload,
    survivalState,
    survivalPressure,
    suggestedSurvivalActions,
    recentSurvivalEvents,
  };

  window.addEventListener("rpg:survival_payload", (event) => maybeRenderPayload(safeObj(event.detail)));
  window.addEventListener("rpg:turn_payload", (event) => maybeRenderPayload(safeObj(event.detail)));
  window.addEventListener("rpg:inspector_payload", (event) => maybeRenderPayload(safeObj(event.detail)));

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installFetchObserver);
  } else {
    installFetchObserver();
  }
})();
