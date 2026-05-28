const fs = require('fs');
const vm = require('vm');

const sourcePath = process.argv[2];
if (!sourcePath) throw new Error('missing command bridge source path');

function assert(condition, message) {
  if (!condition) throw new Error(message || 'assertion failed');
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = '';
    this.focused = false;
    this.events = [];
  }
  dispatchEvent(event) {
    this.events.push(event.type);
  }
  focus() {
    this.focused = true;
  }
}

function makeContext(options) {
  options = options || {};
  const input = new FakeElement('message-input');
  const dispatched = [];
  const sent = [];
  const document = {
    getElementById: (id) => (id === 'message-input' || id === 'rpg-command-input') && options.withInput !== false ? input : null,
    querySelector: () => options.withInput !== false ? input : null,
  };
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
  function Event(type, init) {
    this.type = type;
    this.bubbles = !!(init && init.bubbles);
  }
  const window = {
    dispatchEvent: (event) => {
      dispatched.push(event);
      if (options.preventSubmit && event.type === 'rpg:submit_command') {
        event.preventDefault();
        return false;
      }
      return true;
    },
  };
  if (options.directSender) {
    window.rpgSendMessage = (command, meta) => sent.push({ command, meta, method: 'rpgSendMessage' });
  }
  if (options.clientSender) {
    window.RpgClient = { sendCommand: (command, meta) => sent.push({ command, meta, method: 'RpgClient.sendCommand' }) };
  }
  const context = { console, document, window, CustomEvent, Event };
  context.globalThis = context;
  return { context, input, dispatched, sent };
}

const source = fs.readFileSync(sourcePath, 'utf8');

const direct = makeContext({ directSender: true });
vm.runInNewContext(source, direct.context, { filename: sourcePath });
let result = direct.context.window.RpgCommandBridge.submitCommand('drink water', { action_type: 'survival' });
assert(result.handled === true, 'direct sender was not handled');
assert(result.method === 'rpgSendMessage', `expected rpgSendMessage got ${result.method}`);
assert(direct.sent[0].command === 'drink water', 'direct sender command mismatch');

const client = makeContext({ clientSender: true });
vm.runInNewContext(source, client.context, { filename: sourcePath });
result = client.context.window.RpgCommandBridge.submitCommand('eat rations', { action_type: 'survival' });
assert(result.handled === true, 'client sender was not handled');
assert(result.method === 'RpgClient.sendCommand', `expected client sender got ${result.method}`);
assert(client.sent[0].command === 'eat rations', 'client sender command mismatch');

const eventOnly = makeContext({ preventSubmit: true, withInput: true });
vm.runInNewContext(source, eventOnly.context, { filename: sourcePath });
result = eventOnly.context.window.RpgCommandBridge.submitCommand('rest', { action_type: 'survival' });
assert(result.handled === true, 'cancelable event was not handled');
assert(result.method === 'event', `expected event got ${result.method}`);
assert(eventOnly.dispatched[0].type === 'rpg:submit_command', 'submit event not dispatched');
assert(eventOnly.dispatched[0].detail.command === 'rest', 'event command mismatch');
assert(eventOnly.input.value === '', 'input should not be used when event handled');

const inputFallback = makeContext({ withInput: true });
vm.runInNewContext(source, inputFallback.context, { filename: sourcePath });
result = inputFallback.context.window.RpgCommandBridge.submitCommand('buy water', { action_type: 'survival' });
assert(result.handled === true, 'input fallback was not handled');
assert(result.method === 'input', `expected input got ${result.method}`);
assert(inputFallback.input.value === 'buy water', 'input value mismatch');
assert(inputFallback.input.focused === true, 'input was not focused');
assert(inputFallback.input.events.includes('input'), 'input event missing');

const empty = makeContext({ withInput: false });
vm.runInNewContext(source, empty.context, { filename: sourcePath });
result = empty.context.window.RpgCommandBridge.submitCommand('   ', { action_type: 'survival' });
assert(result.handled === false, 'empty command should not be handled');
assert(result.method === 'empty', 'empty command method mismatch');

console.log(JSON.stringify({ ok: true, direct: direct.sent[0].command, event: eventOnly.dispatched[0].detail.command, input: inputFallback.input.value }));
