const fs = require('fs');
const vm = require('vm');

const sourcePath = process.argv[2];
const commandBridgePath = process.argv[3];
if (!sourcePath) {
  throw new Error('missing survival inspector source path');
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message || 'assertion failed');
  }
}

class FakeElement {
  constructor(tagName, documentRef) {
    this.tagName = String(tagName || 'div').toUpperCase();
    this.documentRef = documentRef;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.parentNode = null;
    this._innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.style = {};
  }

  set id(value) {
    this.attributes.id = String(value || '');
    if (this.documentRef && this.attributes.id) {
      this.documentRef.nodesById[this.attributes.id] = this;
    }
  }

  get id() {
    return this.attributes.id || '';
  }

  set className(value) {
    this.attributes.class = String(value || '');
  }

  get className() {
    return this.attributes.class || '';
  }

  set innerHTML(value) {
    this._innerHTML = String(value || '');
    this.children = [];
    const buttonRe = /<button\b([^>]*)>([\s\S]*?)<\/button>/g;
    let match;
    while ((match = buttonRe.exec(this._innerHTML)) !== null) {
      const button = new FakeElement('button', this.documentRef);
      button.parentNode = this;
      button._innerHTML = match[2];
      button.textContent = match[2].replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
      const attrs = match[1] || '';
      const attrRe = /([a-zA-Z0-9_:\-]+)="([^"]*)"/g;
      let attrMatch;
      while ((attrMatch = attrRe.exec(attrs)) !== null) {
        button.setAttribute(attrMatch[1], attrMatch[2]);
      }
      this.children.push(button);
    }
  }

  get innerHTML() {
    return this._innerHTML;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    if (child.id && this.documentRef) {
      this.documentRef.nodesById[child.id] = child;
    }
    return child;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value || '');
    if (name === 'id') this.id = value;
    if (name === 'class') this.className = value;
    if (name.indexOf('data-') === 0) {
      const key = name.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
      this.dataset[key] = String(value || '');
    }
  }

  getAttribute(name) {
    return this.attributes[name] || '';
  }

  addEventListener(type, handler) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(handler);
  }

  dispatchEvent(event) {
    const handlers = this.listeners[event.type] || [];
    handlers.forEach((handler) => handler.call(this, event));
  }

  click() {
    this.dispatchEvent({ type: 'click', target: this });
  }

  focus() {
    this.focused = true;
  }

  querySelectorAll(selector) {
    const out = [];
    const visit = (node) => {
      if (selector === '[data-rpg-survival-command]' && node.attributes['data-rpg-survival-command']) {
        out.push(node);
      }
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return out;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

class FakeDocument {
  constructor() {
    this.nodesById = {};
    this.readyState = 'complete';
    this.head = new FakeElement('head', this);
    this.body = new FakeElement('body', this);
    this.listeners = {};
    const commandInput = new FakeElement('textarea', this);
    commandInput.id = 'message-input';
    this.body.appendChild(commandInput);
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
  }

  getElementById(id) {
    return this.nodesById[id] || null;
  }

  querySelector(selector) {
    if (selector === "textarea, input[type='text']") {
      return this.getElementById('message-input');
    }
    if (selector === '[data-rpg-inspector]') return null;
    return null;
  }

  addEventListener(type, handler) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(handler);
  }
}

const document = new FakeDocument();
const submitted = [];
const submitEvents = [];
function CustomEvent(type, init) {
  this.type = type;
  this.detail = (init && init.detail) || {};
  this.bubbles = !!(init && init.bubbles);
  this.cancelable = !!(init && init.cancelable);
  this.defaultPrevented = false;
  this.preventDefault = () => {
    if (this.cancelable) this.defaultPrevented = true;
  };
}
const context = {
  console,
  CustomEvent,
  Event: function Event(type, init) { this.type = type; Object.assign(this, init || {}); },
  document,
  window: {
    document,
    __submitted: submitted,
    rpgSendMessage: (command) => submitted.push(command),
    dispatchEvent: (event) => {
      if (event.type === 'rpg:submit_command') submitEvents.push(event);
      return true;
    },
    addEventListener: () => {},
  },
};
context.globalThis = context;

if (commandBridgePath) {
  vm.runInNewContext(fs.readFileSync(commandBridgePath, 'utf8'), context, { filename: commandBridgePath });
}
const source = fs.readFileSync(sourcePath, 'utf8');
vm.runInNewContext(source, context, { filename: sourcePath });

assert(context.window.RpgSurvivalInspector, 'RpgSurvivalInspector was not exported');

const payload = {
  result: {
    survival: {
      enabled: true,
      hunger: 58,
      thirst: 91,
      fatigue: 33,
      events: [
        { kind: 'survival_tick', reason: 'travel_turn', source: 'runtime_survival_tick', effects: { hunger: 2, thirst: 3 } },
        { kind: 'drink_water', source: 'runtime_survival_action', inventory_delta: { water: -1 } },
      ],
    },
    survival_pressure: { hunger: 'high', thirst: 'critical', fatigue: 'moderate' },
    survival_action_context: {
      suggested_actions: [
        { action_id: 'survival:drink_water', action: 'drink water', action_type: 'survival', reason: 'critical thirst' },
        { action_id: 'survival:eat_rations', action: 'eat rations', action_type: 'survival', reason: 'high hunger' },
      ],
    },
    survival_tick_result: { applied: true, reason: 'travel_turn', source: 'runtime_survival_tick' },
  },
};

context.window.RpgSurvivalInspector.render(payload);
const panel = document.getElementById('rpg-survival-inspector-panel');
assert(panel, 'survival panel was not created');
assert(panel.dataset.hasSurvival === 'true', 'panel did not mark survival payload as present');
assert(panel.innerHTML.includes('Hunger'), 'hunger need was not rendered');
assert(panel.innerHTML.includes('Thirst'), 'thirst need was not rendered');
assert(panel.innerHTML.includes('Fatigue'), 'fatigue need was not rendered');
assert(panel.innerHTML.includes('rpg-survival-need--critical'), 'critical pressure class was not rendered');
assert(panel.innerHTML.includes('travel_turn'), 'tick reason was not rendered');
assert(panel.innerHTML.includes('drink water'), 'drink water action was not rendered');
assert(panel.innerHTML.includes('eat rations'), 'eat rations action was not rendered');
assert(panel.innerHTML.includes('survival_tick'), 'survival event was not rendered');

const buttons = panel.querySelectorAll('[data-rpg-survival-command]');
assert(buttons.length === 2, 'expected two survival command buttons');
buttons[0].click();
assert(submitted.length === 1, 'click did not submit a survival command');
assert(submitted[0] === 'drink water', `expected drink water, got ${submitted[0]}`);
assert(buttons[0].dataset.submitHandled === 'true', 'submit handled dataset missing');
assert(buttons[0].dataset.submitMethod === 'rpgSendMessage', `unexpected submit method ${buttons[0].dataset.submitMethod}`);

const derivedPayload = { result: { survival: { hunger: 10, thirst: 76, fatigue: 51 } } };
const derivedPressure = context.window.RpgSurvivalInspector.survivalPressure(derivedPayload);
assert(derivedPressure.thirst === 'critical', 'derived critical pressure failed');
assert(derivedPressure.fatigue === 'high', 'derived high pressure failed');

console.log(JSON.stringify({ ok: true, buttons: buttons.length, submitted: submitted[0], method: buttons[0].dataset.submitMethod }));
