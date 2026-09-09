import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function (pi: ExtensionAPI) {
  const runId = process.env.OMNIX_AGENT_RUN_ID || "";
  const baseUrl = process.env.OMNIX_AGENT_BROKER_URL || "http://127.0.0.1:8000/api/agent-runs";
  const allowed = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_EXTERNAL_CAPABILITIES || "[]"));
  const localAllowed = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_LOCAL_CAPABILITIES || "[]"));
  let usedManagedWorkspacePreview = false;
  if (!runId) return;

  pi.registerTool({
    name: "omnix_plan",
    label: "Omnix Plan",
    description: "Persist or inspect the coding agent's working plan. Ordinary in-scope edits are advisory; Omnix requires hard plan authority only for consequential mutations.",
    promptSnippet: "Working plans are informative; use hard planning when Omnix explicitly requires it",
    promptGuidelines: [
      "Use your normal Pi planning/replanning loop for ordinary coding. A working plan is useful for audit/recovery/review context but is not permission for normal in-scope source/test edits.",
      "Do not stop to amend the plan merely because you discover another ordinary in-scope caller or test while implementing.",
      "Use action=inspect only when an explicit deterministic repository search would help your own reasoning or provide audit evidence; Omnix does not infer semantic task lenses for you.",
      "If Omnix blocks a consequential mutation because hard planning authority is required, submit or amend a narrow plan covering that exact path/command, then retry it.",
      "Use action=check for diagnostics when useful; advisory conformance is not completion authority.",
      "Plan approval never grants capabilities, external authority, or user approval. Workspace, capability, approval, budget, and final acceptance policies remain independent.",
    ],
    parameters: Type.Object({
      action: Type.Union([
        Type.Literal("inspect"),
        Type.Literal("submit"),
        Type.Literal("amend"),
        Type.Literal("check"),
      ]),
      queries: Type.Optional(Type.Array(Type.String())),
      paths: Type.Optional(Type.Array(Type.String())),
      plan: Type.Optional(Type.Record(Type.String(), Type.Any())),
    }),
    async execute(_toolCallId, params, signal) {
      const action = String(params.action || "");
      const response = await fetch(`${baseUrl}/${encodeURIComponent(runId)}/planning/${encodeURIComponent(action)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          action === "inspect"
            ? { queries: params.queries || [], paths: params.paths || [] }
            : action === "check"
              ? {}
              : { plan: params.plan || {} },
        ),
        signal,
      });
      let payload: any = {};
      try {
        payload = await response.json();
      } catch {
        payload = { detail: `HTTP ${response.status}` };
      }
      if (!response.ok) {
        return {
          content: [{ type: "text", text: `Omnix planning error: ${JSON.stringify(payload)}` }],
          details: { error: true, payload },
        };
      }
      return {
        content: [{ type: "text", text: JSON.stringify(payload) }],
        details: payload,
      };
    },
  });

  if (localAllowed.has("workspace.run_change_set")) {
    pi.registerTool({
      name: "omnix_change_set",
      label: "Omnix Run Change Set",
      description: "Read the canonical complete run-owned change subject for the exact current candidate. This, not shell git diff, is final-diff authority.",
      promptSnippet: "Inspect the authoritative baseline-relative RunChangeSet",
      promptGuidelines: [
        "Use this tool for final-diff inspection. The returned subject is baseline-relative and includes run-added untracked content references.",
        "The exact workspace may contain baseline dirties; treat them as context, not run-owned subject paths.",
      ],
      parameters: Type.Object({}),
      async execute(_toolCallId, _params, signal) {
        const response = await fetch(`${baseUrl}/${encodeURIComponent(runId)}/run-change-set`, { signal });
        let payload: any = {};
        try { payload = await response.json(); } catch { payload = { detail: `HTTP ${response.status}` }; }
        if (!response.ok) {
          return { content: [{ type: "text", text: `Omnix change-set error: ${JSON.stringify(payload)}` }], details: { error: true, payload } };
        }
        return { content: [{ type: "text", text: JSON.stringify(payload) }], details: payload };
      },
    });
  }

  if (allowed.size === 0) return;

  pi.registerTool({
    name: "omnix_capability",
    label: "Omnix Capability",
    description: "Invoke one canonical external capability issued by Omnix. Mutations may require approval.",
    promptSnippet: "Use governed Omnix capabilities for external systems",
    promptGuidelines: [
      "Use omnix_capability only with capability IDs issued in the task authority.",
      "If omnix_capability reports approval is required, do not claim the action happened; wait for approval and retry with the approval_id.",
      "For local web/UI validation, call browser.open with input { workspace_preview: true, path: '/<route>' } instead of starting npm/vite through the shell. Omnix owns the exact-worktree preview lifecycle and automatically cleans it up after a passing deterministic browser assertion.",
      "After a managed workspace preview has been used, do not request browser.close for cleanup; Omnix owns cleanup and suppresses redundant close calls so they cannot create approval waits.",
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
      if (params.capability_id === "browser.close" && usedManagedWorkspacePreview) {
        return {
          content: [{ type: "text", text: "Managed workspace preview cleanup is Omnix-owned; no explicit browser.close call is required." }],
          details: {
            capability_id: "browser.close",
            executed: true,
            approval_required: false,
            managed_cleanup: true,
          },
        };
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
      if (
        params.capability_id === "browser.open"
        && params.input?.workspace_preview === true
        && payload.executed === true
      ) {
        usedManagedWorkspacePreview = true;
      }
      return { content: [{ type: "text", text: JSON.stringify(payload.result) }], details: payload };
    },
  });
}
