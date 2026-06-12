(function () {
  "use strict";

  const PANEL_ID = "rpg-next-action-buttons-panel";
  const SOURCE = "phase14_24_next_action_buttons_ui";

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
    return safeStr(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
  }

  function rootPayload(payload) {
    payload = safeObj(payload);
    return safeObj(payload.result || payload);
  }

  function buttonPayload(payload) {
    const root = rootPayload(payload);
    return safeObj(
      payload.next_action_buttons ||
      root.next_action_buttons ||
      safeObj(payload.player_agency_contract).next_action_buttons ||
      safeObj(root.player_agency_contract).next_action_buttons
    );
  }

  function normalizeButtons(payload) {
    const panel = buttonPayload(payload);
    const seen = new Set();
    return safeArr(panel.buttons).filter((button) => {
      button = safeObj(button);
      const id = safeStr(button.id).trim();
      const command = safeStr(button.submit_command || button.command).trim();
      if (!id || !command || seen.has(id)) return false;
      seen.add(id);
      return true;
    }).slice(0, 8).map((button) => {
      button = safeObj(button);
      return {
        id: safeStr(button.id).trim(),
        label: safeStr(button.label || button.submit_command || button.command || "Action").trim(),
        description: safeStr(button.description).trim(),
        submit_command: safeStr(button.submit_command || button.command).trim(),
        action_type: safeStr(button.action_type).trim(),
        tone_tags: safeArr(button.tone_tags).map((tag) => safeStr(tag).trim()).filter(Boolean).slice(0, 5),
        validation_required: button.validation_required !== false,
        presentation_only: button.presentation_only !== false,
      };
    });
  }

  function ensureStyle() {
    if (document.getElementById("rpg-next-action-buttons-style")) return;
    const style = document.createElement("style");
    style.id = "rpg-next-action-buttons-style";
    style.textContent = `
      .rpg-next-action-buttons-panel {
        margin: 10px 0;
        padding: 10px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 12px;
        background: rgba(0, 0, 0, 0.18);
      }
      .rpg-next-action-buttons-header {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: baseline;
        margin-bottom: 8px;
      }
      .rpg-next-action-buttons-title {
        font-size: 0.88rem;
        font-weight: 700;
      }
      .rpg-next-action-buttons-note {
        font-size: 0.75rem;
        opacity: 0.72;
      }
      .rpg-next-action-buttons-list {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .rpg-next-action-btn {
        display: inline-flex;
        flex-direction: column;
        gap: 3px;
        max-width: min(100%, 280px);
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 10px;
        padding: 8px 10px;
        background: rgba(255, 255, 255, 0.08);
        color: inherit;
        cursor: pointer;
        text-align: left;
      }
      .rpg-next-action-btn:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.14);
      }
      .rpg-next-action-btn:disabled {
        cursor: not-allowed;
        opacity: 0.55;
      }
      .rpg-next-action-btn-label {
        font-weight: 700;
      }
      .rpg-next-action-btn-description {
        font-size: 0.78rem;
        opacity: 0.78;
        line-height: 1.25;
      }
      .rpg-next-action-btn-command {
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        font-size: 0.72rem;
        opacity: 0.68;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .rpg-next-action-tone-tags {
        display: flex;
        gap: 4px;
        flex-wrap: wrap;
      }
      .rpg-next-action-tone-tag {
        border-radius: 999px;
        padding: 1px 6px;
        background: rgba(255, 255, 255, 0.1);
        font-size: 0.68rem;
        opacity: 0.82;
      }
    `;
    document.head.appendChild(style);
  }

  function hostNode() {
    return (
      document.getElementById("rpgChoicePanel") ||
      document.getElementById("rpg-service-actions") ||
      document.getElementById("rpgNarrativeFeed") ||
      document.getElementById("rpgView") ||
      document.body
    );
  }

  function ensurePanel() {
    ensureStyle();
    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;
    panel = document.createElement("section");
    panel.id = PANEL_ID;
    panel.className = "rpg-next-action-buttons-panel";
    panel.style.display = "none";
    const host = hostNode();
    if (host && host.parentNode && host.id === "rpgChoicePanel") {
      host.parentNode.insertBefore(panel, host);
    } else if (host && host.parentNode && host.id === "rpgNarrativeFeed") {
      host.parentNode.insertBefore(panel, host.nextSibling);
    } else if (host && host.appendChild) {
      host.appendChild(panel);
    }
    return panel;
  }

  function submitCommand(command) {
    command = safeStr(command).trim();
    if (!command) return false;

    const input = document.getElementById("messageInput") || document.getElementById("rpg-command-input") || document.querySelector("textarea");
    const sendBtn = document.getElementById("sendBtn") || document.getElementById("rpg-send-btn") || document.querySelector("button[type='submit']");

    if (input) {
      input.value = command;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.focus();
    }
    if (sendBtn && !sendBtn.disabled) {
      sendBtn.click();
      return true;
    }
    if (typeof window.rpgSendMessage === "function") {
      window.rpgSendMessage(command);
      return true;
    }
    if (typeof window.sendRpgMessage === "function") {
      window.sendRpgMessage(command);
      return true;
    }
    return false;
  }

  function render(payload) {
    const buttons = normalizeButtons(payload);
    const panel = ensurePanel();
    if (!panel) return;
    if (!buttons.length) {
      panel.innerHTML = "";
      panel.style.display = "none";
      return;
    }

    const buttonHtml = buttons.map((button) => {
      const toneTags = button.tone_tags.length
        ? `<div class="rpg-next-action-tone-tags">${button.tone_tags.map((tag) => `<span class="rpg-next-action-tone-tag">${escapeHtml(tag)}</span>`).join("")}</div>`
        : "";
      return `
        <button type="button" class="rpg-next-action-btn" data-next-action-id="${escapeHtml(button.id)}" data-submit-command="${escapeHtml(button.submit_command)}" title="Submits: ${escapeHtml(button.submit_command)}">
          <span class="rpg-next-action-btn-label">${escapeHtml(button.label)}</span>
          ${button.description ? `<span class="rpg-next-action-btn-description">${escapeHtml(button.description)}</span>` : ""}
          ${toneTags}
          <span class="rpg-next-action-btn-command">↳ ${escapeHtml(button.submit_command)}</span>
        </button>
      `;
    }).join("");

    panel.innerHTML = `
      <div class="rpg-next-action-buttons-header">
        <div class="rpg-next-action-buttons-title">Possible next actions</div>
        <div class="rpg-next-action-buttons-note">Buttons submit the preserved command. You can still type anything.</div>
      </div>
      <div class="rpg-next-action-buttons-list">${buttonHtml}</div>
    `;
    panel.style.display = "";

    panel.querySelectorAll(".rpg-next-action-btn").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.disabled) return;
        const command = button.getAttribute("data-submit-command") || "";
        submitCommand(command);
      });
    });
  }

  function isRpgTurnUrl(url) {
    const text = safeStr(url);
    return text.indexOf("/api/rpg/session/turn") >= 0;
  }

  function installFetchWatcher() {
    if (window.__rpgNextActionButtonsFetchInstalled) return;
    if (typeof window.fetch !== "function") return;
    const originalFetch = window.fetch.bind(window);
    window.__rpgNextActionButtonsFetchInstalled = true;
    window.fetch = function patchedFetch(input, init) {
      const url = typeof input === "string" ? input : safeStr(input && input.url);
      const isTurn = isRpgTurnUrl(url);
      if (isTurn) {
        const panel = document.getElementById(PANEL_ID);
        if (panel) {
          panel.querySelectorAll("button").forEach((button) => { button.disabled = true; });
        }
      }
      return originalFetch(input, init).then((response) => {
        if (isTurn && response && response.clone) {
          response.clone().json().then((payload) => {
            render(payload);
          }).catch(() => {});
        }
        return response;
      });
    };
  }

  function init() {
    ensurePanel();
    installFetchWatcher();
  }

  window.RpgNextActionButtons = {
    render,
    normalizeButtons,
    submitCommand,
    installFetchWatcher,
    source: SOURCE,
  };

  window.addEventListener("rpg:next_action_buttons", (event) => {
    render(safeObj(event.detail));
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
