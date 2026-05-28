const fs = require('fs');
const vm = require('vm');

const sourcePath = process.argv[2];
if (!sourcePath) throw new Error('missing live payload bridge source path');

function assert(condition, message) {
  if (!condition) throw new Error(message || 'assertion failed');
}

const events = [];
const document = {
  readyState: 'complete',
  addEventListener: () => {},
};

function CustomEvent(type, init) {
  this.type = type;
  this.detail = (init && init.detail) || {};
}

const window = {
  addEventListener: () => {},
  dispatchEvent: (event) => {
    events.push({ type: event.type, detail: event.detail });
  },
  fetch: () => Promise.resolve({
    ok: true,
    status: 200,
    clone: () => ({
      json: () => Promise.resolve({
        ok: true,
        result: {
          turn_id: 'turn:1',
          survival: { hunger: 10, thirst: 80, fatigue: 20 },
          survival_pressure: { hunger: 'low', thirst: 'critical', fatigue: 'low' },
        },
      }),
    }),
  }),
};

const context = { console, document, window, CustomEvent, setTimeout, clearTimeout };
context.globalThis = context;

const source = fs.readFileSync(sourcePath, 'utf8');
vm.runInNewContext(source, context, { filename: sourcePath });

assert(context.window.RpgLivePayloadBridge, 'RpgLivePayloadBridge was not exported');
assert(context.window.RpgLivePayloadBridge.hasSurvivalEvidence({ result: { survival: { thirst: 80 } } }), 'survival evidence not detected');
assert(context.window.RpgLivePayloadBridge.isRpgPayload({ result: { turn_id: 'turn:1' } }), 'RPG payload not detected');

const payload = {
  ok: true,
  turn_contract: { turn_id: 'turn:manual' },
  result: {
    survival: { hunger: 55, thirst: 75, fatigue: 12 },
    survival_action_context: { suggested_actions: [{ action_id: 'survival:drink_water', action: 'drink water' }] },
  },
};
const dispatched = context.window.RpgLivePayloadBridge.dispatchRpgPayload(payload, { url: '/api/rpg/session/turn' });
assert(dispatched === true, 'dispatchRpgPayload returned false');
assert(events.some((event) => event.type === 'rpg:turn_payload'), 'turn payload event missing');
assert(events.some((event) => event.type === 'rpg:survival_payload'), 'survival payload event missing');
assert(events.every((event) => event.detail.meta.source === 'rpg_live_payload_bridge'), 'event source missing');

context.window.fetch('/api/rpg/session/turn').then(() => new Promise((resolve) => setTimeout(resolve, 0))).then(() => {
  assert(events.filter((event) => event.type === 'rpg:turn_payload').length >= 2, 'fetch bridge did not dispatch turn payload');
  assert(events.filter((event) => event.type === 'rpg:survival_payload').length >= 2, 'fetch bridge did not dispatch survival payload');
  console.log(JSON.stringify({ ok: true, events: events.map((event) => event.type) }));
}).catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
