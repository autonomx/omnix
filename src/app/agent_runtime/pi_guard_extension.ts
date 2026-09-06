import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import fs from "node:fs";
import path from "node:path";

const workspace = path.resolve(process.env.OMNIX_AGENT_WORKSPACE || process.cwd());
const realWorkspace = fs.realpathSync(workspace);
const runId = process.env.OMNIX_AGENT_RUN_ID || "";
const brokerUrl = process.env.OMNIX_AGENT_BROKER_URL || "http://127.0.0.1:8000/api/agent-runs";
const approvalPolicy = process.env.OMNIX_AGENT_APPROVAL_POLICY || "ask_sensitive";

function stringList(name: string, fallback: string[]): string[] {
  try {
    const parsed = JSON.parse(process.env[name] || "");
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : fallback;
  } catch {
    return fallback;
  }
}

const allowedPaths = stringList("OMNIX_AGENT_ALLOWED_PATHS", ["**"]);
const forbiddenPaths = stringList("OMNIX_AGENT_FORBIDDEN_PATHS", []);
const localCapabilities = new Set(stringList("OMNIX_AGENT_LOCAL_CAPABILITIES", []));

function relativeWorkspacePath(value: string): string | null {
  const cleaned = value.startsWith("@") ? value.slice(1) : value;
  const resolved = path.resolve(workspace, cleaned);
  const relative = path.relative(workspace, resolved);
  if (relative === ".." || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) return null;
  return (relative || ".").split(path.sep).join("/");
}

function globRegex(pattern: string): RegExp {
  let value = pattern.split("\\").join("/");
  value = value.replace(/[.+^$(){}|[\]\\]/g, "\\$&");
  value = value.replace(/\*\*/g, "__DOUBLE_STAR__");
  value = value.replace(/\*/g, "[^/]*");
  value = value.replace(/\?/g, "[^/]");
  value = value.replace(/__DOUBLE_STAR__/g, ".*");
  return new RegExp("^" + value + "$");
}

function matches(patterns: string[], relative: string): boolean {
  return patterns.some((pattern) => {
    if (pattern === "**") return true;
    const normalized = pattern.split("\\").join("/");
    if (normalized.endsWith("/**") && relative === normalized.slice(0, -3)) {
      return true;
    }
    return globRegex(normalized).test(relative);
  });
}

function realPathWithinWorkspace(value: string): boolean {
  const cleaned = value.startsWith("@") ? value.slice(1) : value;
  const candidate = path.resolve(workspace, cleaned);
  let probe = candidate;
  while (true) {
    try {
      fs.lstatSync(probe);
      break;
    } catch {
      const parent = path.dirname(probe);
      if (parent === probe) return false;
      probe = parent;
    }
  }
  let realProbe: string;
  try {
    realProbe = fs.realpathSync(probe);
  } catch {
    // A dangling symlink (or other unresolvable existing path) is not a safe
    // parent for a read/write target.
    return false;
  }
  const suffix = path.relative(probe, candidate);
  const reconstructed = path.resolve(realProbe, suffix);
  const relative = path.relative(realWorkspace, reconstructed);
  return !(
    relative === ".."
    || relative.startsWith(".." + path.sep)
    || path.isAbsolute(relative)
  );
}

function pathAllowed(value: unknown): boolean {
  if (typeof value !== "string" || !value.trim()) return true;
  const relative = relativeWorkspacePath(value);
  if (relative === null || !realPathWithinWorkspace(value)) return false;
  if (matches(forbiddenPaths, relative)) return false;
  return allowedPaths.length === 0 || matches(allowedPaths, relative);
}

const safeCommandPrefixes = [
  "git status", "git diff", "git log", "git show", "git grep",
  "python -m pytest", "python -m py_compile", "pytest", "ruff",
  "npm test", "npm run test", "npm run build", "npm --prefix", "npm run typecheck", "npm run lint",
  "npm ci --ignore-scripts",
  "npx vitest", "npx tsc",
];

const testCommandPrefixes = [
  "python -m pytest", "pytest", "npm test", "npm run test", "npm --prefix", "npx vitest",
];

const gitStatusCommandPrefixes = ["git status"];
const gitDiffCommandPrefixes = ["git diff"];

function issuedCommandPrefixes(): string[] {
  if (localCapabilities.has("workspace.command")) return safeCommandPrefixes;
  const prefixes = new Set<string>();
  if (localCapabilities.has("workspace.test")) {
    for (const prefix of testCommandPrefixes) prefixes.add(prefix);
  }
  if (localCapabilities.has("workspace.git_status")) {
    for (const prefix of gitStatusCommandPrefixes) prefixes.add(prefix);
  }
  if (localCapabilities.has("workspace.git_diff")) {
    for (const prefix of gitDiffCommandPrefixes) prefixes.add(prefix);
  }
  return [...prefixes];
}

const forbiddenShellSyntax = /[\r\n;&|><`]/;
const environmentExpansion = /(?:\$\{|\$[A-Za-z_]|%[A-Za-z_][A-Za-z0-9_]*%|~[\\/])/;

function commandScopeAllowed(command: string): boolean {
  if (environmentExpansion.test(command)) return false;
  const tokens = command.match(/"[^"]*"|\'[^\']*\'|\S+/g) || [];
  for (const rawToken of tokens.slice(1)) {
    let token = rawToken.replace(/^["\']|["\']$/g, "");
    if (!token) continue;
    const equalsIndex = token.indexOf("=");
    if (token.startsWith("-")) {
      if (equalsIndex < 0) continue;
      token = token.slice(equalsIndex + 1);
    } else if (equalsIndex >= 0) {
      token = token.slice(equalsIndex + 1);
    }
    if (!token) continue;
    const normalized = token.replace(/\\/g, "/");
    if (normalized === ".." || normalized.startsWith("../") || normalized.includes("/../")) return false;
    const looksLikePath = path.isAbsolute(token) || token.includes("/") || token.includes("\\") || token.startsWith(".");
    if (looksLikePath && !pathAllowed(token)) return false;
  }
  return true;
}

function commandSafetyRejectionReason(command: unknown): string | null {
  if (typeof command !== "string" || !command.trim()) {
    return "Omnix command policy requires a non-empty command.";
  }
  const normalized = command.trim().toLowerCase();
  if (forbiddenShellSyntax.test(normalized) || normalized.includes("$(")) {
    return "Omnix command policy blocks shell chaining, pipes, redirection, command substitution, and multi-command syntax. Run each allowed command as a separate tool call.";
  }
  if (!commandScopeAllowed(command)) {
    return "Omnix command policy blocked an out-of-scope path or unsafe environment/path expansion. Keep command paths inside the issued workspace.";
  }
  return null;
}

function commandPrefixAllowed(command: string): boolean {
  const normalized = command.trim().toLowerCase().replace(/^(npx|npm|python)\.cmd(?=\s|$)/, "$1");
  return issuedCommandPrefixes().some((prefix) => normalized === prefix || normalized.startsWith(prefix + " "));
}

function commandRejectionReason(command: unknown): string | null {
  const safetyRejection = commandSafetyRejectionReason(command);
  if (safetyRejection) return safetyRejection;
  if (typeof command !== "string" || !commandPrefixAllowed(command)) {
    const prefixes = issuedCommandPrefixes();
    return `Omnix command policy does not allow that command prefix. Use one of: ${prefixes.join(", ") || "no shell commands issued"}.`;
  }
  return null;
}

async function authorizeBlockedCommand(command: string, cwd: unknown): Promise<string | null> {
  if (!runId) return "Omnix run identity is missing.";
  try {
    const response = await fetch(`${brokerUrl}/${encodeURIComponent(runId)}/command-authorization`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        command,
        cwd: typeof cwd === "string" ? cwd : workspace,
        workspace_root: workspace,
      }),
    });
    let payload: any = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (response.ok && payload?.allowed === true) return null;
    if (response.ok && payload?.approval_required === true) {
      return `Omnix approval required for this exact workspace command (approval ${String(payload.approval_id || "pending")}). Ask the user to approve it in Omnix, then retry the same command.`;
    }
    const detail = typeof payload?.detail === "string"
      ? payload.detail
      : typeof payload?.reason === "string" ? payload.reason : `HTTP ${response.status}`;
    return `Omnix command permission denied: ${detail}`;
  } catch (error) {
    return `Omnix command permission service unavailable: ${String(error)}`;
  }
}

async function authorizeWorkspaceTool(toolName: string, input: Record<string, unknown>): Promise<string | null> {
  if (!runId) return "Omnix run identity is missing.";
  try {
    const response = await fetch(`${brokerUrl}/${encodeURIComponent(runId)}/workspace-authorization`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_name: toolName, input, workspace_root: workspace }),
    });
    let payload: any = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (response.ok && payload?.allowed === true) return null;
    if (response.ok && payload?.approval_required === true) {
      return `Omnix approval required for this exact workspace ${toolName} action (approval ${String(payload.approval_id || "pending")}). Ask the user to approve it in Omnix, then retry the same action.`;
    }
    const detail = typeof payload?.detail === "string"
      ? payload.detail
      : typeof payload?.reason === "string" ? payload.reason : `HTTP ${response.status}`;
    return `Omnix workspace permission denied: ${detail}`;
  } catch (error) {
    return `Omnix workspace permission service unavailable: ${String(error)}`;
  }
}

async function authorizeTool(toolName: string): Promise<string | null> {
  if (!runId) return "Omnix run identity is missing.";
  try {
    const response = await fetch(`${brokerUrl}/${encodeURIComponent(runId)}/budget/tool`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_name: toolName }),
    });
    if (response.ok) return null;
    let detail = "tool budget authorization failed";
    try {
      const payload = await response.json();
      detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
    return `Omnix budget blocked this tool call: ${detail}`;
  } catch (error) {
    return `Omnix budget authorization unavailable: ${String(error)}`;
  }
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    const input = (event as any).input || {};
    if (["read", "edit", "write", "grep", "find", "ls"].includes(event.toolName)) {
      for (const key of ["path", "file", "directory", "cwd"]) {
        if (!pathAllowed(input[key])) return { block: true, reason: "Omnix workspace policy blocked a path outside the issued scope." };
      }
      if (
        (event.toolName === "edit" || event.toolName === "write")
        && approvalPolicy === "always_ask"
        && localCapabilities.has(`workspace.${event.toolName}`)
      ) {
        const permissionRejection = await authorizeWorkspaceTool(event.toolName, input);
        if (permissionRejection) return { block: true, reason: permissionRejection };
      }
    }
    if (event.toolName === "bash" || event.toolName === "powershell") {
      const safetyRejection = commandSafetyRejectionReason(input.command);
      if (safetyRejection) return { block: true, reason: safetyRejection };
      const commandAllowedByIssuedCapability = commandPrefixAllowed(input.command);
      if (!commandAllowedByIssuedCapability && !localCapabilities.has("workspace.command")) {
        const rejection = commandRejectionReason(input.command);
        if (rejection) return { block: true, reason: rejection };
      }
      const commandNeedsApproval = localCapabilities.has("workspace.command")
        && approvalPolicy !== "allow_automatic"
        && (approvalPolicy === "always_ask" || !commandAllowedByIssuedCapability);
      if (commandNeedsApproval) {
        const permissionRejection = await authorizeBlockedCommand(input.command as string, input.cwd);
        if (permissionRejection) return { block: true, reason: permissionRejection };
      }
    }
    const budgetError = await authorizeTool(event.toolName);
    if (budgetError) return { block: true, reason: budgetError };
  });
}
