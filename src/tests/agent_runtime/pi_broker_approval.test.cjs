const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

async function main() {
  const source = fs.readFileSync(path.resolve(__dirname, "../../app/agent_runtime/pi_broker_extension.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    reportDiagnostics: true,
  });
  assert.deepEqual(compiled.diagnostics, []);
  const registered = [];
  const sent = [];
  let response = { approval_required: true, approval_id: "opaque-server-token" };
  const exports = {};
  vm.runInNewContext(compiled.outputText, {
    exports,
    require(name) {
      assert.equal(name, "typebox");
      return { Type: new Proxy({}, { get: (_, kind) => (...args) => ({ kind, args }) }) };
    },
    process: { env: {
      OMNIX_AGENT_RUN_ID: "run-one",
      OMNIX_AGENT_EXTERNAL_CAPABILITIES: '["gmail.send_email"]',
    } },
    fetch: async (_url, options) => {
      sent.push(JSON.parse(options.body));
      return { ok: true, json: async () => response };
    },
  });
  exports.default({ registerTool: tool => registered.push(tool) });
  const tool = registered.find(tool => tool.name === "omnix_capability");
  assert.ok(tool);
  assert.equal(tool.parameters.args[0].approval_id, undefined);
  const first = await tool.execute("call-one", {
    capability_id: "gmail.send_email", input: { to: "example", body: "Hi" },
  });
  assert.equal(sent[0].approval_id, undefined);
  assert.equal(JSON.stringify(first).includes("opaque-server-token"), false);
  assert.equal(JSON.stringify(first).includes("approval_id"), false);
  response = { executed: true, result: { sent: true, approval_id: "nested-token" }, approval_id: "opaque-server-token" };
  const retry = await tool.execute("call-two", {
    capability_id: "gmail.send_email", input: { body: "Hi", to: "example" },
  });
  assert.equal(sent[1].approval_id, "opaque-server-token");
  assert.equal(sent[1].proposal_id, "call-two");
  assert.equal(JSON.stringify(retry).includes("token"), false);
  assert.equal(JSON.stringify(retry).includes("approval_id"), false);
  await tool.execute("call-three", {
    capability_id: "gmail.send_email", input: { body: "Changed", to: "example" },
  });
  assert.equal(sent[2].approval_id, undefined);
  console.log("Pi approval identity and retry tests passed.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
