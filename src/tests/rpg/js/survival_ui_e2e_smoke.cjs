const fs = require('fs');
const vm = require('vm');

const commandBridgePath = process.argv[2];
const survivalInspectorPath = process.argv[3];
if (!commandBridgePath || !survivalInspectorPath) {
  throw new Error('missing command bridge or survival inspector source path');
}

function assert(condition, message) {
  if (!condition) throw new Error(message || 'assertion failed');
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
    this.value = '';
    this.focused = false;
    this.style = {};
  }
  set id(value) {
    this.attributes.id = String(value || '');
    if (this.documentRef && this.attributes.id) this.documentRef.nodesById[this.attributes.id] = this;
  }
  get id() { return this.attributes.id || ''; }
  set className(value) { this.attributes.class = String(value || ''); }
  get className() { return this.attributes.class || ''; }
  set innerHTML(value) {
    this._innerHTML = String(value || '');
    this.children = [];
    const buttonRe = /<button\b([^>]*)>([\s\S]*?)<\/button>/g;
    let match;
    while ((match = buttonRe.exec(this._innerHTML)) !== null) {
      const button = new FakeElement('button', this.documentRef);
      button.parentNode = this;
      const attrs = match[1] || '';
      const attrRe = /([a-zA-Z0-9_:\-]+)="([^"]*)"/g;
      let attrMatch;
      while ((attrMatch = attrRe.exec(attrs)) !== null) button.setAttribute(attrMatch[1], attrMatch[2]);
      this.children.push(button);
    }
  }
  get innerHTML() { return this._innerHTML; }
  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    if (child.id && this.documentRef) this.documentRef.nodesById[child.id] = child;
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
  getAttribute(name) { return this.attributes[name] || ''; }
  addEventListener(type, handler) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(handler);
  }
  dispatchEvent(event) { (this.listeners[event.type] || []).forEach((handler) => handler.call(this, event)); }
  click() { this.dispatchEvent({ type: 'click', target: this }); }
  focus() { this.focused = true; }
  querySelectorAll(selector) {
    const out = [];
    const visit = (node) => {
      if (selector === '[data-rpg-survival-command]' && node.attributes['data-rpg-survival-command']) out.push(node);
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return out;
  }
}

class FakeDocument {
  constructor() {
    this.nodesById = {};
    this.readyState = 'complete';
    this.head = new FakeElement('head', this);
    this.body = new FakeElement('body', this);
    this.listeners = {};
    const input = new FakeElement('textarea', this);
    input.id = 'message-input';
    this.body.appendChild(input);
  }
  createElement(tagName) { return new FakeElement(tagName, this); }
  getElementById(id) { return this.nodesById[id] || null; }
  querySelector(selector) { return selector === "textarea, input[type='text']" ? this.getElementById('message-input') : null; }
  addEventListener(type, handler) { this.listeners[type] = this.listeners[type] || []; this.listeners[type].push(handler); }
}

function CustomEvent(type, init) {
  this.type = type;
  this.detail = (init && init.detail) || {};
  this.cancelable = !!(init && init.cancelable);
  this.defaultPrevented = false;
  this.preventDefault = () => { if (this.cancelable) this.defaultPrevented = true; };
}
function Event(type, init) { this.type = type; Object.assign(this, init || {}); }

const document = new FakeDocument();
const submitted = [];
const responses = {
  'drink water': { result: { survival: { hunger: 60, thirst: 35, fatigue: 20, events: [{ kind: 'drink_water' }] }, survival_pressure: { hunger: 'high', thirst: 'moderate', fatigue: 'low' }, survival_action_context: { suggested_actions: [{ action_id: 'survival:eat_rations', action: 'eat rations', action_type: 'survival' }] } } },
  'eat rations': { result: { survival: { hunger: 20, thirst: 35, fatigue: 20, events: [{ kind: 'eat_rations' }] }, survival_pressure: { hunger: 'low', thirst: 'moderate', fatigue: 'low' }, survival_action_context: { suggested_actions: [] } } },
};
const window = {
  document,
  addEventListener: () => {},
  dispatchEvent: () => true,
  rpgSendMessage: (command) => {
    submitted.push(command);
    const response = responses[command];
    if (response) window.RpgSurvivalInspector.render(response);
  },
};
const context = { console, document, window, CustomEvent, Event };
context.globalThis = context;

vm.runInNewContext(fs.readFileSync(commandBridgePath, 'utf8'), context, { filename: commandBridgePath });
vm.runInNewContext(fs.readFileSync(survivalInspectorPath, 'utf8'), context, { filename: survivalInspectorPath });

window.RpgSurvivalInspector.render({
  result: {
    survival: { hunger: 60, thirst: 90, fatigue: 20, events: [] },
    survival_pressure: { hunger: 'high', thirst: 'critical', fatigue: 'low' },
    survival_action_context: { suggested_actions: [{ action_id: 'survival:drink_water', action: 'drink water', action_type: 'survival' }] },
  },
});
let panel = document.getElementById('rpg-survival-inspector-panel');
let buttons = panel.querySelectorAll('[data-rpg-survival-command]');
assert(buttons.length === 1, 'initial drink button missing');
buttons[0].click();
assert(submitted[0] === 'drink water', 'drink command not submitted');
assert(panel.innerHTML.includes('Thirst'), 'panel did not rerender after drink');
assert(panel.innerHTML.includes('eat rations'), 'eat rations follow-up not rendered');
buttons = panel.querySelectorAll('[data-rpg-survival-command]');
buttons[0].click();
assert(submitted[1] === 'eat rations', 'eat command not submitted');
assert(panel.innerHTML.includes('No survival action pressure right now'), 'final no-pressure state not rendered');

console.log(JSON.stringify({ ok: true, submitted }));
