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
    const chrome = window.RpgPanelChrome;
    if (chrome && typeof chrome.escapeHtml === "function") return chrome.escapeHtml(value);
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
  }

  function firstNonEmptyObj(values) {
    for (const value of values) {
      const candidate = safeObj(value);
      if (Object.keys(candidate).length) return candidate;
    }
    return {};
  }

  function inventoryPartyPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    const hud = firstNonEmptyObj([
      root.player_hud,
      result.player_hud,
      safeObj(root.resolved_result).player_hud,
      safeObj(root.narration_context).player_hud,
    ]);
    return firstNonEmptyObj([
      root.inventory_party_panel,
      result.inventory_party_panel,
      safeObj(root.resolved_result).inventory_party_panel,
      safeObj(root.narration_context).inventory_party_panel,
      hud,
    ]);
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function ensureInventoryPartyHost() {
    let panel = document.getElementById("rpgInventoryPartyPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgInventoryPartyPanel";
      panel.className = "rpg-inventory-party-panel";
      const chrome = chromeHelper();
      if (chrome && typeof chrome.decoratePanel === "function") {
        chrome.decoratePanel(panel, "inventory-party", "deterministic_phase8_inventory_party_detail_panel");
      } else {
        host.appendChild(panel);
      }
    }

    panel.style.display = "block";
    return panel;
  }

  function normalizeCurrency(payload) {
    payload = safeObj(payload);
    const resources = safeObj(payload.resources || payload.resource_summary || payload);
    const currency = safeObj(resources.currency || resources.coins || payload.currency);
    return {
      gold: currency.gold ?? resources.gold ?? 0,
      silver: currency.silver ?? resources.silver ?? 0,
      copper: currency.copper ?? resources.copper ?? 0,
    };
  }

  function normalizeInventoryItems(payload) {
    payload = safeObj(payload);
    const resources = safeObj(payload.resources || payload.resource_summary || payload);
    const candidates = safeArr(payload.inventory || payload.items || resources.inventory || resources.items);
    return candidates.map((item, index) => {
      const obj = safeObj(item);
      const itemId = safeStr(obj.item_id || obj.id || obj.name || `item-${index}`);
      return {
        itemId,
        label: safeStr(obj.label || obj.name || itemId || "Item"),
        quantity: obj.quantity ?? obj.count ?? 1,
        summary: safeStr(obj.summary || obj.description || obj.kind || "Inventory item"),
      };
    });
  }

  function normalizePartyMembers(payload) {
    payload = safeObj(payload);
    const candidates = safeArr(payload.party || payload.party_members || payload.companions);
    return candidates.map((member, index) => {
      const obj = safeObj(member);
      const memberId = safeStr(obj.actor_id || obj.member_id || obj.id || obj.name || `member-${index}`);
      return {
        memberId,
        label: safeStr(obj.name || obj.label || memberId || "Party member"),
        role: safeStr(obj.role || obj.relationship || obj.status || "Companion"),
        summary: safeStr(obj.summary || obj.current_activity || obj.location || "Travelling with the player"),
      };
    });
  }

  function renderCurrency(currency) {
    currency = safeObj(currency);
    return `
      <dl class="rpg-inventory-currency">
        <div><dt>Gold</dt><dd>${escapeHtml(currency.gold ?? 0)}</dd></div>
        <div><dt>Silver</dt><dd>${escapeHtml(currency.silver ?? 0)}</dd></div>
        <div><dt>Copper</dt><dd>${escapeHtml(currency.copper ?? 0)}</dd></div>
      </dl>
    `;
  }

  function renderItem(item) {
    item = safeObj(item);
    const itemId = safeStr(item.itemId || "item");
    const label = safeStr(item.label || itemId || "Item");
    const quantity = safeStr(item.quantity ?? 1);
    const summary = safeStr(item.summary || "Inventory item");
    return `
      <li class="rpg-inventory-item" data-item-id="${escapeHtml(itemId)}">
        <strong>${escapeHtml(label)}</strong>
        <span>Qty ${escapeHtml(quantity)}</span>
        <em>${escapeHtml(summary)}</em>
      </li>
    `;
  }

  function renderPartyMember(member) {
    member = safeObj(member);
    const memberId = safeStr(member.memberId || "member");
    const label = safeStr(member.label || memberId || "Party member");
    const role = safeStr(member.role || "Companion");
    const summary = safeStr(member.summary || "Travelling with the player");
    return `
      <li class="rpg-party-member" data-member-id="${escapeHtml(memberId)}">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(role)}</span>
        <em>${escapeHtml(summary)}</em>
      </li>
    `;
  }

  function renderInventoryPartyPanel(payload) {
    const panelPayload = inventoryPartyPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensureInventoryPartyHost();
    const source = safeStr(panelPayload.frontend_source || panelPayload.source || "deterministic_phase8_inventory_party_detail_panel");
    const currency = normalizeCurrency(panelPayload);
    const items = normalizeInventoryItems(panelPayload);
    const members = normalizePartyMembers(panelPayload);
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(source, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Inventory and party details are read-only; commands still go through runtime validation.") : "<p class=\"rpg-inventory-party-guidance\">Commands still go through runtime validation.</p>";
    const emptyItems = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No inventory items are currently visible.", "Runtime payloads have not supplied source-backed inventory entries yet.") : "<p>No inventory items are currently visible.</p>";
    const emptyMembers = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No party members are currently visible.", "Runtime payloads have not supplied source-backed party entries yet.") : "<p>No party members are currently visible.</p>";

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(target, "inventory-party", source);
    }

    target.innerHTML = `
      <div class="rpg-inventory-party" data-source="${escapeHtml(source)}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-inventory-party-header">
          <span>Inventory & Party</span>
          ${sourceBadge}
          <em>Read-only inventory and party details from deterministic turn payloads.</em>
        </div>
        ${runtimeNotice}
        <section class="rpg-inventory-currency-section">
          <h4>Currency</h4>
          ${renderCurrency(currency)}
        </section>
        <section class="rpg-inventory-items">
          <h4>Inventory</h4>
          ${items.length ? `<ul>${items.map(renderItem).join("")}</ul>` : emptyItems}
        </section>
        <section class="rpg-party-members">
          <h4>Party</h4>
          ${members.length ? `<ul>${members.map(renderPartyMember).join("")}</ul>` : emptyMembers}
        </section>
      </div>
    `;
    return true;
  }

  window.RpgInventoryPartyPanel = {
    render: renderInventoryPartyPanel,
    inventoryPartyPayloadFromTurnPayload,
    normalizeCurrency,
    normalizeInventoryItems,
    normalizePartyMembers,
    renderCurrency,
    renderItem,
    renderPartyMember,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderInventoryPartyPanel(payload);
        return previousRender(payload);
      },
      renderInventoryPartyPanel,
    });
  }
})();
