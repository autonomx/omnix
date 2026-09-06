import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const baseUrl =
    process.env.OMNIX_AGENT_MODEL_GATEWAY_URL ||
    "http://127.0.0.1:8000/api/agent-model/v1";
  const runId = process.env.OMNIX_AGENT_RUN_ID || "";
  const sessionId = process.env.OMNIX_AGENT_MODEL_SESSION_ID || "";
  const modelKey = process.env.OMNIX_AGENT_MODEL_KEY || "";
  const modelId = process.env.OMNIX_AGENT_MODEL_ID || modelKey;
  const reasoningEffort = (process.env.OMNIX_AGENT_REASONING_EFFORT || "").trim().toLowerCase();
  const reasoning = Boolean(reasoningEffort) && !["off", "none", "disabled"].includes(reasoningEffort);

  if (!runId || !modelKey) {
    throw new Error("Omnix agent model provider requires run/model identity");
  }

  pi.registerProvider("omnix", {
    name: "Omnix Model Gateway",
    baseUrl,
    apiKey: "omnix-local",
    api: "openai-completions",
    headers: {
      "X-Omnix-Agent-Run-Id": runId,
      ...(sessionId ? { "X-Omnix-Agent-Session-Id": sessionId } : {}),
    },
    models: [
      {
        id: modelKey,
        name: `Omnix: ${modelId}`,
        reasoning,
        input: ["text", "image"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 200000,
        maxTokens: 65536,
      },
    ],
  });
}
