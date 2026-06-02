(function () {
  "use strict";

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function safeArr(value) {
    return Array.isArray(value) ? value : [];
  }

  function safeStr(value) {
    return value == null ? "" : String(value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function firstNonEmptyObj(values) {
    for (const value of values) {
      const candidate = safeObj(value);
      if (Object.keys(candidate).length) return candidate;
    }
    return {};
  }

  function objectiveJournalPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return firstNonEmptyObj([
      root.objective_journal_panel,
      result.objective_journal_panel,
      safeObj(root.resolved_result).objective_journal_panel,
      safeObj(root.narration_context).objective_journal_panel,
    ]);
  }

  function ensureObjectiveJournalHost() {
    let panel = document.getElementById("rpgObjectiveJournalPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgObjectiveJournalPanel";
      panel.className = "rpg-objective-journal-panel";
      host.appendChild(panel);
    }

    panel.style.display = "block";
    return panel;
  }

  function renderObjective(objective) {
    objective = safeObj(objective);
    const title = safeStr(objective.title || "Objective");
    const status = safeStr(objective.status_label || objective.status || "Available");
    const description = safeStr(objective.description || "");
    const blockingReason = safeStr(objective.blocking_reason || "");

    return `
      <li class="rpg-objective-journal-objective is-${escapeHtml(objective.status || "available")}">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(status)}</span>
        ${description ? `<p>${escapeHtml(description)}</p>` : ""}
        ${blockingReason ? `<em>${escapeHtml(blockingReason)}</em>` : ""}
      </li>
    `;
  }

  function renderObjectiveGroup(label, items) {
    items = safeArr(items);
    return `
      <section class="rpg-objective-journal-group">
        <h4>${escapeHtml(label)}</h4>
        ${items.length ? `<ul>${items.map(renderObjective).join("")}</ul>` : `<p>No ${escapeHtml(label.toLowerCase())} objectives.</p>`}
      </section>
    `;
  }

  function renderJournalEntry(entry) {
    entry = safeObj(entry);
    const title = safeStr(entry.title || "Journal entry");
    const body = safeStr(entry.body || "");
    return `
      <li class="rpg-objective-journal-entry">
        <strong>${escapeHtml(title)}</strong>
        ${body ? `<p>${escapeHtml(body)}</p>` : ""}
      </li>
    `;
  }

  function renderWarning(warning) {
    warning = safeObj(warning);
    const severity = safeStr(warning.severity || "info");
    const label = safeStr(warning.label || warning.kind || "Warning");
    return `<li class="rpg-objective-journal-warning is-${escapeHtml(severity)}">${escapeHtml(label)}</li>`;
  }

  function renderRecentAction(actionState) {
    actionState = safeObj(actionState);
    const actionType = safeStr(actionState.action_type || "none");
    const reason = safeStr(actionState.reason || actionState.summary || "");
    const status = actionState.ok === true ? "applied" : "not applied";
    return `
      <div class="rpg-objective-journal-action-state">
        <span>Recent action</span>
        <strong>${escapeHtml(actionType)}</strong>
        <em>${escapeHtml(status)}</em>
        ${reason ? `<p>${escapeHtml(reason)}</p>` : ""}
      </div>
    `;
  }

  function renderObjectiveJournalPanel(payload) {
    const panelPayload = objectiveJournalPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensureObjectiveJournalHost();
    const activeObjective = safeObj(panelPayload.active_objective);
    const objectives = safeObj(panelPayload.objectives);
    const journalEntries = safeArr(panelPayload.journal_entries);
    const warnings = safeArr(panelPayload.major_warnings);
    const source = safeStr(panelPayload.frontend_source || panelPayload.source);

    target.innerHTML = `
      <div class="rpg-objective-journal" data-source="${escapeHtml(source)}">
        <div class="rpg-objective-journal-header">
          <span>Objectives & Journal</span>
          <em>Source: ${escapeHtml(source)}</em>
        </div>
        <section class="rpg-objective-journal-active">
          <span>Active objective</span>
          <strong>${escapeHtml(activeObjective.title || "No active objective recorded")}</strong>
          <em>${escapeHtml(activeObjective.status_label || activeObjective.status || "None")}</em>
        </section>
        <div class="rpg-objective-journal-groups">
          ${renderObjectiveGroup("Active", safeArr(objectives.active))}
          ${renderObjectiveGroup("Available", safeArr(objectives.available))}
          ${renderObjectiveGroup("Completed", safeArr(objectives.completed))}
          ${renderObjectiveGroup("Blocked", safeArr(objectives.blocked))}
        </div>
        <section class="rpg-objective-journal-entries">
          <h4>Recent journal</h4>
          ${journalEntries.length ? `<ul>${journalEntries.map(renderJournalEntry).join("")}</ul>` : "<p>No journal entries recorded.</p>"}
        </section>
        ${renderRecentAction(panelPayload.recent_action_state)}
        ${warnings.length ? `<ul class="rpg-objective-journal-warnings">${warnings.map(renderWarning).join("")}</ul>` : ""}
      </div>
    `;
    return true;
  }

  window.RpgObjectiveJournalPanel = {
    render: renderObjectiveJournalPanel,
    objectiveJournalPayloadFromTurnPayload,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderObjectiveJournalPanel(payload);
        return previousRender(payload);
      },
      renderObjectiveJournalPanel,
    });
  }
})();
