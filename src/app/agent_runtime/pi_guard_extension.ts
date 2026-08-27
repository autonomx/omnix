import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import path from "node:path";

const workspace = path.resolve(process.env.OMNIX_AGENT_WORKSPACE || process.cwd());
const runId = process.env.OMNIX_AGENT_RUN_ID || "";
const brokerUrl = process.env.OMNIX_AGENT_BROKER_URL || "http://127.0.0.1:8000/api/agent-runs";

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

function pathAllowed(value: unknown): boolean {
  if (typeof value !== "string" || !value.trim()) return true;
  const relative = relativeWorkspacePath(value);
  if (relative === null) return false;
  if (matches(forbiddenPaths, relative)) return false;
  return allowedPaths.length === 0 || matches(allowedPaths, relative);
}

const safeCommandPrefixes = [
  "git status", "git diff", "git log", "git show", "git grep",
  "python -m pytest", "python -m py_compile", "pytest", "ruff",
  "npm test", "npm run test", "npm run typecheck", "npm run lint",
  "npx vitest", "npx tsc",
];

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

function commandAllowed(command: unknown): boolean {
  if (typeof command !== "string") return false;
  const normalized = command.trim().toLowerCase();
  if (!normalized || forbiddenShellSyntax.test(normalized) || normalized.includes("$(")) return false;
  if (!safeCommandPrefixes.some((prefix) => normalized === prefix || normalized.startsWith(prefix + " "))) return false;
  return commandScopeAllowed(command);
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
    }
    if ((event.toolName === "bash" || event.toolName === "powershell") && !commandAllowed(input.command)) {
      return { block: true, reason: "Omnix command policy blocked this command or an out-of-scope path." };
    }
    const budgetError = await authorizeTool(event.toolName);
    if (budgetError) return { block: true, reason: budgetError };
  });
}
