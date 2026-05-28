(function () {
  "use strict";

  const SOURCE = "rpg_command_bridge";

  function safeStr(value) {
    return value == null ? "" : String(value);
  }

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function dispatchSubmitCommandEvent(command, meta) {
    try {
      const event = new CustomEvent("rpg:submit_command", {
        bubbles: true,
        cancelable: true,
        detail: {
          command: command,
          meta: Object.assign({ source: SOURCE }, safeObj(meta)),
        },
      });
      const allowed = window.dispatchEvent(event);
      return {
        dispatched: true,
        handled: event.defaultPrevented === true || allowed === false,
        default_prevented: event.defaultPrevented === true,
        method: "event",
        source: SOURCE,
      };
    } catch (error) {
      return {
        dispatched: false,
        handled: false,
        error: safeStr(error && (error.message || error)),
        method: "event_error",
        source: SOURCE,
      };
    }
  }

  function fallbackToInput(command) {
    const input =
      document.getElementById("rpg-command-input") ||
      document.getElementById("message-input") ||
      document.querySelector("textarea, input[type='text']");
    if (!input) {
      return { handled: false, method: "none", source: SOURCE };
    }
    input.value = command;
    try {
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } catch (_) {}
    if (typeof input.focus === "function") {
      input.focus();
    }
    return { handled: true, method: "input", source: SOURCE };
  }

  function callDirectSender(command, meta) {
    const directSenders = [
      { name: "rpgSendMessage", fn: window.rpgSendMessage },
      { name: "sendRpgMessage", fn: window.sendRpgMessage },
      { name: "RpgClient.sendCommand", fn: safeObj(window.RpgClient).sendCommand },
      { name: "RpgClient.sendMessage", fn: safeObj(window.RpgClient).sendMessage },
    ];
    for (const sender of directSenders) {
      if (typeof sender.fn !== "function") continue;
      try {
        sender.fn.call(window.RpgClient || window, command, meta);
        return { handled: true, method: sender.name, source: SOURCE };
      } catch (error) {
        return {
          handled: false,
          method: sender.name,
          error: safeStr(error && (error.message || error)),
          source: SOURCE,
        };
      }
    }
    return { handled: false, method: "none", source: SOURCE };
  }

  function submitCommand(command, meta) {
    command = safeStr(command).trim();
    meta = Object.assign({ source: SOURCE }, safeObj(meta));
    if (!command) {
      return { handled: false, method: "empty", source: SOURCE };
    }

    const direct = callDirectSender(command, meta);
    if (direct.handled) {
      return direct;
    }

    const eventResult = dispatchSubmitCommandEvent(command, meta);
    if (eventResult.handled) {
      return eventResult;
    }

    const inputResult = fallbackToInput(command);
    if (inputResult.handled) {
      return inputResult;
    }

    return {
      handled: false,
      method: "unhandled",
      event_result: eventResult,
      direct_result: direct,
      source: SOURCE,
    };
  }

  window.RpgCommandBridge = {
    submitCommand,
    dispatchSubmitCommandEvent,
    fallbackToInput,
    source: SOURCE,
  };
})();
