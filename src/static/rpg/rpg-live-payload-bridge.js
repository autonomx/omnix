(function () {
  "use strict";

  const SOURCE = "rpg_live_payload_bridge";
  const FLAG = "__rpg_live_payload_bridge_installed";

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function safeStr(value) {
    return value == null ? "" : String(value);
  }

  function hasSurvivalEvidence(payload) {
    payload = safeObj(payload);
    const result = safeObj(payload.result || payload);
    const contract = safeObj(payload.turn_contract || result.turn_contract || payload.turn_contract);
    const session = safeObj(payload.session || result.session);
    const sim = safeObj(session.simulation_state || payload.simulation_state || result.simulation_state);
    const keys = [
      "survival",
      "survival_pressure",
      "survival_action_context",
      "survival_tick_result",
      "survival_result",
      "autoplay_survival_pressure",
    ];
    return keys.some((key) => Object.prototype.hasOwnProperty.call(payload, key)) ||
      keys.some((key) => Object.prototype.hasOwnProperty.call(result, key)) ||
      keys.some((key) => Object.prototype.hasOwnProperty.call(contract, key)) ||
      keys.some((key) => Object.prototype.hasOwnProperty.call(sim, key));
  }

  function isRpgPayload(payload) {
    payload = safeObj(payload);
    const result = safeObj(payload.result);
    return !!(
      payload.turn_contract ||
      payload.session ||
      payload.session_id ||
      payload.narration ||
      result.turn_id ||
      result.resolved_result ||
      hasSurvivalEvidence(payload)
    );
  }

  function dispatchPayloadEvent(name, payload, meta) {
    try {
      window.dispatchEvent(new CustomEvent(name, {
        detail: {
          payload: payload,
          meta: Object.assign({ source: SOURCE }, safeObj(meta)),
        },
      }));
    } catch (_) {}
  }

  function dispatchRpgPayload(payload, meta) {
    payload = safeObj(payload);
    meta = safeObj(meta);
    if (!isRpgPayload(payload)) return false;
    dispatchPayloadEvent("rpg:turn_payload", payload, meta);
    if (hasSurvivalEvidence(payload)) {
      dispatchPayloadEvent("rpg:survival_payload", payload, meta);
    }
    return true;
  }

  function shouldObserveUrl(url) {
    url = safeStr(url);
    return url.indexOf("/api/rpg") >= 0;
  }

  function installFetchBridge() {
    if (window[FLAG]) return;
    if (typeof window.fetch !== "function") return;
    window[FLAG] = true;
    const originalFetch = window.fetch.bind(window);
    window.fetch = function () {
      const args = arguments;
      return originalFetch.apply(null, args).then((response) => {
        try {
          const request = args[0];
          const url = safeStr(request && (request.url || request));
          if (shouldObserveUrl(url) && response && response.clone) {
            response.clone().json().then((payload) => {
              dispatchRpgPayload(payload, {
                url: url,
                status: response.status,
                ok: response.ok,
                bridge: "fetch",
              });
            }).catch(() => {});
          }
        } catch (_) {}
        return response;
      });
    };
  }

  window.RpgLivePayloadBridge = {
    dispatchRpgPayload,
    hasSurvivalEvidence,
    isRpgPayload,
    installFetchBridge,
    source: SOURCE,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installFetchBridge);
  } else {
    installFetchBridge();
  }
})();
