import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function (pi: ExtensionAPI) {
  const runId = process.env.OMNIX_AGENT_RUN_ID || "";
  const baseUrl = process.env.OMNIX_AGENT_BROKER_URL || "http://127.0.0.1:8000/api/agent-runs";
  const allowed = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_EXTERNAL_CAPABILITIES || "[]"));
  if (!runId || allowed.size === 0) return;

  pi.registerTool({
    name: "omnix_capability",
    label: "Omnix Capability",
    description: "Invoke one canonical external capability issued by Omnix. Mutations may require approval.",
    promptSnippet: "Use governed Omnix capabilities for external systems",
    promptGuidelines: [
      "Use omnix_capability only with capability IDs issued in the task authority.",
      "If omnix_capability reports approval is required, do not claim the action happened; wait for approval and retry with the approval_id.",
    ],
    parameters: Type.Object({
      capability_id: Type.String(),
      input: Type.Optional(Type.Record(Type.String(), Type.Any())),
      approval_id: Type.Optional(Type.String()),
    }),
    async execute(toolCallId, params, signal) {
      if (!allowed.has(params.capability_id)) {
        return { content: [{ type: "text", text: "Blocked: capability is outside the issued Omnix RunSpec." }], details: { blocked: true } };
      }
      const response = await fetch(`${baseUrl}/${encodeURIComponent(runId)}/capabilities/${params.capability_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: params.input || {}, approval_id: params.approval_id, proposal_id: toolCallId }),
        signal,
      });
      const payload = await response.json();
      if (!response.ok) return { content: [{ type: "text", text: `Omnix broker error: ${JSON.stringify(payload)}` }], details: { error: true, payload } };
      if (payload.approval_required) return { content: [{ type: "text", text: `Approval required before ${params.capability_id}. approval_id=${payload.approval_id}` }], details: payload };
      return { content: [{ type: "text", text: JSON.stringify(payload.result) }], details: payload };
    },
  });
}
