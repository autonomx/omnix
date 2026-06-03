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
    const chrome = window.RpgPanelChrome;
    if (chrome && typeof chrome.escapeHtml === "function") return chrome.escapeHtml(value);
    return safeStr(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function clampPct(value) {
    return Math.max(0, Math.min(100, Math.round(safeNum(value, 0))));
  }

  function unwrapPayload(payload) {
    payload = safeObj(payload);
    return safeObj(payload.payload || payload);
  }

  function resultRoot(payload) {
    payload = unwrapPayload(payload);
    return safeObj(payload.result || payload);
  }

  function turnContractRoot(payload) {
    payload = unwrapPayload(payload);
    return safeObj(payload.turn_contract || safeObj(payload.result).turn_contract || payload);
  }

  function simulationRoot(payload) {
    payload = unwrapPayload(payload);
    return safeObj(
      payload.simulation_state ||
      safeObj(payload.session).simulation_state ||
      safeObj(safeObj(payload.result).session).simulation_state ||
      safeObj(payload.result).simulation_state
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
    survival = safeObj(survival || survivalState(payload));
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

  function inventoryRoot(payload) {
    const result = resultRoot(payload);
    const sim = simulationRoot(payload);
    const player = safeObj(sim.player_state || result.player_state || safeObj(result.session).player_state);
    return firstObj(result.inventory, player.inventory, player.inventory_state, sim.inventory);
  }

  function itemSearchText(item) {
    item = safeObj(item);
    return [
      item.item_id,
      item.definition_id,
      item.name,
      item.kind,
      ...safeArr(item.tags),
      ...safeArr(item.aliases),
    ].map(safeStr).join(" ").toLowerCase().replace(/[_:]/g, " ");
  }

  function countInventoryTerms(payload, terms) {
    const inventory = inventoryRoot(payload);
    const items = safeArr(inventory.items);
    let total = 0;
    terms = terms.map((term) => safeStr(term).toLowerCase());
    items.forEach((item) => {
      const search = itemSearchText(item);
      if (!terms.some((term) => search.indexOf(term) >= 0)) return;
      total += Math.max(1, safeNum(safeObj(item).quantity, 1));
    });
    return total;
  }

  function waterskinCharges(payload) {
    const inventory = inventoryRoot(payload);
    for (const item of safeArr(inventory.items)) {
      const search = itemSearchText(item);
      if (search.indexOf("waterskin") < 0 && search.indexOf("water skin") < 0) continue;
      const metadata = safeObj(safeObj(item).metadata);
      const state = safeObj(safeObj(item).state);
      if (metadata.water_charges != null) return safeNum(metadata.water_charges, 0);
      if (state.water_charges != null) return safeNum(state.water_charges, 0);
    }
    return 0;
  }

  function currencySummary(payload) {
    const result = resultRoot(payload);
    const sim = simulationRoot(payload);
    const player = safeObj(sim.player_state || result.player_state);
    const inventory = inventoryRoot(payload);
    const currency = safeObj(inventory.currency || player.currency);
    const parts = [];
    if (safeNum(currency.gold, 0)) parts.push(`${safeNum(currency.gold, 0)}g`);
    if (safeNum(currency.silver, 0)) parts.push(`${safeNum(currency.silver, 0)}s`);
    if (safeNum(currency.copper, 0)) parts.push(`${safeNum(currency.copper, 0)}c`);
    return parts.join(" ") || "no coin";
  }

  function survivalInventorySummary(payload) {
    return {
      water: countInventoryTerms(payload, ["water"]),
      rations: countInventoryTerms(payload, ["ration", "rations", "food", "meal"]),
      waterskin: countInventoryTerms(payload, ["waterskin", "water skin"]),
      waterskin_charges: waterskinCharges(payload),
      currency: currencySummary(payload),
    };
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
    const chrome = chromeHelper();
    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(panel, "survival-inspector", SOURCE);
    } else {
      findHost().appendChild(panel);
    }
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
      <div class="rpg-survival-need rpg-survival-need--${escapeHtml(pressureClass(label))}" title="${escapeHtml(name)} pressure is ${pct}/100 (${label})">
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

  function actionAvailability(row, inventory) {
    const command = actionCommand(row).toLowerCase();
    if (command.indexOf("drink") >= 0 && command.indexOf("waterskin") >= 0) return `${inventory.waterskin_charges} waterskin charges`;
    if (command.indexOf("drink") >= 0) return `${inventory.water} water · ${inventory.waterskin_charges} waterskin charges`;
    if (command.indexOf("eat") >= 0) return `${inventory.rations} food/rations`;
    if (command.indexOf("fill waterskin") >= 0) return inventory.waterskin ? `${inventory.waterskin} waterskin` : "needs waterskin";
    if (command.indexOf("buy") >= 0 || command.indexOf("meal") >= 0 || command.indexOf("lodging") >= 0) return `${inventory.currency} available`;
    if (command.indexOf("rest") >= 0 || command.indexOf("sleep") >= 0 || command.indexOf("camp") >= 0) return "service/rest action";
    return safeStr(row.availability || row.inventory_hint || "survival");
  }

  function renderInventorySummary(inventory) {
    return `
      <div class="rpg-survival-inventory" title="Survival inventory snapshot from authoritative runtime payload">
        <span>Water: <strong>${escapeHtml(inventory.water)}</strong></span>
        <span>Waterskin: <strong>${escapeHtml(inventory.waterskin_charges)}</strong> charges</span>
        <span>Food: <strong>${escapeHtml(inventory.rations)}</strong></span>
        <span>Coin: <strong>${escapeHtml(inventory.currency)}</strong></span>
      </div>
    `;
  }

  function renderActions(actions, inventory) {
    const chrome = chromeHelper();
    if (!actions.length) {
      return chrome && typeof chrome.panelEmptyState === "function"
        ? chrome.panelEmptyState("No survival action pressure right now.", "Runtime payloads have not supplied source-backed survival actions yet.")
        : '<div class="rpg-survival-empty">No survival action pressure right now.</div>';
    }
    return actions.map((row) => {
      const command = actionCommand(row);
      const availability = actionAvailability(row, inventory);
      const reason = safeStr(row.reason || row.need || row.pressure || "survival");
      return `
        <button type="button" class="rpg-survival-action" data-rpg-survival-command="${escapeHtml(command)}" title="${escapeHtml(reason)} · ${escapeHtml(availability)}">
          <span>${escapeHtml(command)}</span>
          <small>${escapeHtml(reason)}</small>
          <em class="rpg-survival-action-availability">${escapeHtml(availability)}</em>
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
    const serviceType = safeStr(safeObj(event.service_result).service_type);
    return [kind, serviceType, deltas, inv].filter(Boolean).join(" · ");
  }

  function renderEvents(events) {
    const chrome = chromeHelper();
    if (!events.length) {
      return chrome && typeof chrome.panelEmptyState === "function"
        ? chrome.panelEmptyState("No survival events recorded yet.", "Runtime payloads have not supplied source-backed survival events yet.")
        : '<div class="rpg-survival-empty">No survival events recorded yet.</div>';
    }
    return events.map((event) => `
      <div class="rpg-survival-event" title="${escapeHtml(eventLabel(event))}">
        <strong>${escapeHtml(eventLabel(event))}</strong>
        <code>${escapeHtml(event.source || event.tick || "runtime")}</code>
      </div>
    `).join("");
  }

  function submitSurvivalCommand(command) {
    command = safeStr(command).trim();
    if (!command) return { handled: false, method: "empty", source: SOURCE };
    if (window.RpgCommandBridge && typeof window.RpgCommandBridge.submitCommand === "function") {
      return window.RpgCommandBridge.submitCommand(command, {
        source: SOURCE,
        action_type: "survival",
      });
    }
    if (typeof window.rpgSendMessage === "function") {
      window.rpgSendMessage(command);
      return { handled: true, method: "rpgSendMessage", source: SOURCE };
    }
    if (typeof window.sendRpgMessage === "function") {
      window.sendRpgMessage(command);
      return { handled: true, method: "sendRpgMessage", source: SOURCE };
    }
    try {
      const event = new CustomEvent("rpg:submit_command", {
        bubbles: true,
        cancelable: true,
        detail: { command, meta: { source: SOURCE, action_type: "survival" } },
      });
      const allowed = window.dispatchEvent(event);
      if (event.defaultPrevented || allowed === false) {
        return { handled: true, method: "event", source: SOURCE };
      }
    } catch (_) {}
    const input =
      document.getElementById("rpg-command-input") ||
      document.getElementById("message-input") ||
      document.querySelector("textarea, input[type='text']");
    if (input) {
      input.value = command;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
      return { handled: true, method: "input", source: SOURCE };
    }
    return { handled: false, method: "unhandled", source: SOURCE };
  }

  function bindActionButtons(panel) {
    panel.querySelectorAll("[data-rpg-survival-command]").forEach((button) => {
      button.addEventListener("click", () => {
        const result = submitSurvivalCommand(button.getAttribute("data-rpg-survival-command"));
        button.dataset.submitMethod = safeStr(result && result.method);
        button.dataset.submitHandled = result && result.handled ? "true" : "false";
      });
    });
  }

  function render(payload) {
    payload = unwrapPayload(payload);
    const survival = survivalState(payload);
    const pressure = survivalPressure(payload, survival);
    const actions = suggestedSurvivalActions(payload);
    const events = recentSurvivalEvents(payload);
    const tick = latestTickResult(payload);
    const inventory = survivalInventorySummary(payload);
    const panel = ensurePanel();
    const enabled = survival.enabled !== false;
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(SOURCE, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Survival inspector actions still submit commands through runtime validation.") : '<p class="rpg-survival-guidance">Survival inspector actions still submit commands through runtime validation.</p>';

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(panel, "survival-inspector", SOURCE);
    }

    panel.innerHTML = `
      <div class="rpg-survival-inspector" data-source="${escapeHtml(SOURCE)}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-survival-header">
          <div>
            <h3>Survival</h3>
            <div class="rpg-survival-meta">${enabled ? "Runtime pressure" : "Disabled"}${tick.reason ? " · " + escapeHtml(tick.reason) : ""}</div>
          </div>
          ${sourceBadge}
          <span class="rpg-survival-source">${escapeHtml(SOURCE)}</span>
        </div>
        ${runtimeNotice}
        <div class="rpg-survival-needs">
          ${renderNeed("Hunger", survival.hunger, pressure.hunger)}
          ${renderNeed("Thirst", survival.thirst, pressure.thirst)}
          ${renderNeed("Fatigue", survival.fatigue, pressure.fatigue)}
        </div>
        ${renderInventorySummary(inventory)}
        <details class="rpg-survival-details" open>
          <summary>Suggested survival actions (${actions.length})</summary>
          <div class="rpg-survival-actions">${renderActions(actions, inventory)}</div>
        </details>
        <details class="rpg-survival-details">
          <summary>Recent survival events (${events.length})</summary>
          <div class="rpg-survival-events">${renderEvents(events)}</div>
        </details>
      </div>
    `;
    bindActionButtons(panel);
    panel.dataset.hasSurvival = Object.keys(survival).length ? "true" : "false";
    window.__rpg_last_survival_payload = payload;
  }

  function maybeRenderPayload(payload) {
    payload = unwrapPayload(payload);
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
    survivalInventorySummary,
    suggestedSurvivalActions,
    recentSurvivalEvents,
    submitSurvivalCommand,
  };

  window.addEventListener("rpg:survival_payload", (event) => maybeRenderPayload(safeObj(event.detail).payload || safeObj(event.detail)));
  window.addEventListener("rpg:turn_payload", (event) => maybeRenderPayload(safeObj(event.detail).payload || safeObj(event.detail)));
  window.addEventListener("rpg:inspector_payload", (event) => maybeRenderPayload(safeObj(event.detail).payload || safeObj(event.detail)));

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installFetchObserver);
  } else {
    installFetchObserver();
  }
})();