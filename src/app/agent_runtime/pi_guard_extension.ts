import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import path from "node:path";

const workspace = path.resolve(process.env.OMNIX_AGENT_WORKSPACE || process.cwd());

function insideWorkspace(value: unknown): boolean {
  if (typeof value !== "string" || !value.trim()) return true;
  const cleaned = value.startsWith("@") ? value.slice(1) : value;
  const resolved = path.resolve(workspace, cleaned);
  return resolved === workspace || resolved.startsWith(workspace + path.sep);
}

const safeCommandPrefixes = [
  "git status",
  "git diff",
  "git log",
  "git show",
  "git grep",
  "python -m pytest",
  "python -m py_compile",
  "pytest",
  "ruff",
  "npm test",
  "npm run test",
  "npm run typecheck",
  "npm run lint",
  "npx vitest",
  "npx tsc",
];

const forbiddenShellSyntax = /[\r\n;&|><`]/;

function commandAllowed(command: unknown): boolean {
  if (typeof command !== "string") return false;
  const normalized = command.trim().toLowerCase();
  if (!normalized || forbiddenShellSyntax.test(normalized) || normalized.includes("$(")) return false;
  return safeCommandPrefixes.some((prefix) => normalized === prefix || normalized.startsWith(prefix + " "));
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    const input = (event as any).input || {};
    if (["read", "edit", "write", "grep", "find", "ls"].includes(event.toolName)) {
      for (const key of ["path", "file", "directory", "cwd"]) {
        if (!insideWorkspace(input[key])) {
          return { block: true, reason: "Omnix workspace policy blocked a path outside the issued workspace." };
        }
      }
    }
    if (event.toolName === "bash" || event.toolName === "powershell") {
      if (!commandAllowed(input.command)) {
        return { block: true, reason: "Omnix command policy blocked this command. Use only issued development/test commands." };
      }
    }
  });
}
