from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    text = read(path)
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{path}: expected {count} occurrences, found {actual}: {old[:120]!r}")
    write(path, text.replace(old, new, count))


ENGINEERING_EXTENSION = r'''import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

const workspace = path.resolve(process.env.OMNIX_AGENT_WORKSPACE || process.cwd());
const realWorkspace = fs.realpathSync(workspace);
const localCapabilities = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_LOCAL_CAPABILITIES || "[]"));

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

function globRegex(pattern: string): RegExp {
  let value = pattern.split("\\").join("/");
  value = value.replace(/[.+^$(){}|[\]\\]/g, "\\$&");
  value = value.replace(/\*\*/g, "__DOUBLE_STAR__").replace(/\*/g, "[^/]*").replace(/\?/g, "[^/]");
  value = value.replace(/__DOUBLE_STAR__/g, ".*");
  return new RegExp("^" + value + "$");
}

function matches(patterns: string[], relative: string): boolean {
  return patterns.some((pattern) => {
    if (pattern === "**") return true;
    const normalized = pattern.split("\\").join("/");
    if (normalized.endsWith("/**") && relative === normalized.slice(0, -3)) return true;
    return globRegex(normalized).test(relative);
  });
}

function resolveWorkspacePath(value: string): { absolute: string; relative: string } {
  const cleaned = String(value || "").startsWith("@") ? String(value).slice(1) : String(value || "");
  if (!cleaned.trim()) throw new Error("A workspace-relative path is required.");
  const absolute = path.resolve(workspace, cleaned);
  const relativeRaw = path.relative(workspace, absolute);
  if (relativeRaw === ".." || relativeRaw.startsWith(".." + path.sep) || path.isAbsolute(relativeRaw)) {
    throw new Error("Path is outside the issued Omnix workspace.");
  }
  let probe = absolute;
  while (!fs.existsSync(probe)) {
    const parent = path.dirname(probe);
    if (parent === probe) throw new Error("Path has no resolvable workspace ancestor.");
    probe = parent;
  }
  const realProbe = fs.realpathSync(probe);
  const reconstructed = path.resolve(realProbe, path.relative(probe, absolute));
  const realRelative = path.relative(realWorkspace, reconstructed);
  if (realRelative === ".." || realRelative.startsWith(".." + path.sep) || path.isAbsolute(realRelative)) {
    throw new Error("Resolved path escapes the issued Omnix workspace.");
  }
  const relative = (relativeRaw || ".").split(path.sep).join("/");
  if (matches(forbiddenPaths, relative) || (allowedPaths.length && !matches(allowedPaths, relative))) {
    throw new Error("Path is outside the issued Omnix workspace scope.");
  }
  return { absolute, relative };
}

function boundedJson(value: unknown, limit = 18_000): string {
  let text: string;
  try { text = JSON.stringify(value, null, 2); } catch { text = String(value); }
  return text.length <= limit ? text : text.slice(0, limit) + "\n… truncated …";
}

function sha256(value: string | Buffer): string {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function anchor(fileHash: string, lineNumber: number, line: string): string {
  return sha256(`${fileHash}:${lineNumber}:${line}`).slice(0, 10);
}

type LspServerConfig = { command: string; args: string[]; extensions: string[]; language_id: string };

const DEFAULT_LSP_SERVERS: Record<string, LspServerConfig> = {
  typescript: {
    command: "typescript-language-server",
    args: ["--stdio"],
    extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
    language_id: "typescript",
  },
  python: {
    command: "pyright-langserver",
    args: ["--stdio"],
    extensions: [".py", ".pyi"],
    language_id: "python",
  },
};

function lspServers(): Record<string, LspServerConfig> {
  const raw = process.env.OMNIX_AGENT_LSP_SERVERS || "";
  if (!raw.trim()) return DEFAULT_LSP_SERVERS;
  try {
    const decoded = JSON.parse(raw) as Record<string, Partial<LspServerConfig>>;
    const out: Record<string, LspServerConfig> = {};
    for (const [name, row] of Object.entries(decoded || {})) {
      if (!row || typeof row.command !== "string" || !row.command.trim()) continue;
      if (/[;&|><`\r\n]/.test(row.command)) continue;
      out[name] = {
        command: row.command,
        args: Array.isArray(row.args) ? row.args.map(String) : ["--stdio"],
        extensions: Array.isArray(row.extensions) ? row.extensions.map((v) => String(v).toLowerCase()) : [],
        language_id: String(row.language_id || name),
      };
    }
    return Object.keys(out).length ? out : DEFAULT_LSP_SERVERS;
  } catch {
    return DEFAULT_LSP_SERVERS;
  }
}

class LspClient {
  private child: ChildProcessWithoutNullStreams;
  private buffer = Buffer.alloc(0);
  private nextId = 1;
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
  private diagnostics = new Map<string, unknown[]>();
  private initialized: Promise<void>;

  constructor(private config: LspServerConfig) {
    this.child = spawn(config.command, config.args, {
      cwd: workspace,
      env: process.env,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child.stdout.on("data", (chunk: Buffer) => this.onData(chunk));
    this.child.on("error", (error) => this.failAll(error));
    this.child.on("exit", (code) => this.failAll(new Error(`LSP server exited with code ${String(code)}`)));
    this.initialized = this.initialize();
  }

  private failAll(error: Error) {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }

  private onData(chunk: Buffer) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      const headerEnd = this.buffer.indexOf("\r\n\r\n");
      if (headerEnd < 0) return;
      const header = this.buffer.subarray(0, headerEnd).toString("ascii");
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match) {
        this.buffer = this.buffer.subarray(headerEnd + 4);
        continue;
      }
      const length = Number(match[1]);
      const bodyStart = headerEnd + 4;
      if (this.buffer.length < bodyStart + length) return;
      const body = this.buffer.subarray(bodyStart, bodyStart + length).toString("utf8");
      this.buffer = this.buffer.subarray(bodyStart + length);
      let message: any;
      try { message = JSON.parse(body); } catch { continue; }
      if (typeof message?.id === "number" && this.pending.has(message.id)) {
        const pending = this.pending.get(message.id)!;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(String(message.error.message || boundedJson(message.error))));
        else pending.resolve(message.result);
      } else if (message?.method === "textDocument/publishDiagnostics") {
        const uri = String(message.params?.uri || "");
        const rows = Array.isArray(message.params?.diagnostics) ? message.params.diagnostics : [];
        if (uri) this.diagnostics.set(uri, rows);
      }
    }
  }

  private send(message: unknown) {
    const body = JSON.stringify(message);
    this.child.stdin.write(`Content-Length: ${Buffer.byteLength(body, "utf8")}\r\n\r\n${body}`);
  }

  private request(method: string, params: unknown, timeoutMs = 5_000): Promise<unknown> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`LSP request timed out: ${method}`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => { clearTimeout(timer); resolve(value); },
        reject: (error) => { clearTimeout(timer); reject(error); },
      });
      this.send({ jsonrpc: "2.0", id, method, params });
    });
  }

  private notify(method: string, params: unknown) {
    this.send({ jsonrpc: "2.0", method, params });
  }

  private async initialize() {
    await this.request("initialize", {
      processId: process.pid,
      rootUri: pathToFileURL(workspace).href,
      capabilities: {
        textDocument: {
          publishDiagnostics: { relatedInformation: true },
          hover: {}, definition: {}, references: {}, documentSymbol: {}, diagnostic: {},
        },
        workspace: { symbol: {} },
      },
      workspaceFolders: [{ uri: pathToFileURL(workspace).href, name: path.basename(workspace) }],
    }, 8_000);
    this.notify("initialized", {});
  }

  async open(filePath: string): Promise<{ uri: string; text: string }> {
    await this.initialized;
    const resolved = resolveWorkspacePath(filePath);
    const text = fs.readFileSync(resolved.absolute, "utf8");
    const uri = pathToFileURL(resolved.absolute).href;
    this.notify("textDocument/didOpen", {
      textDocument: { uri, languageId: this.config.language_id, version: 1, text },
    });
    return { uri, text };
  }

  async diagnosticsFor(filePath: string): Promise<unknown[]> {
    const { uri } = await this.open(filePath);
    try {
      const pull = await this.request("textDocument/diagnostic", { textDocument: { uri } }, 1_500);
      const items = (pull as any)?.items;
      if (Array.isArray(items)) return items;
    } catch {
      // Many stable language servers still use publishDiagnostics only.
    }
    for (let attempt = 0; attempt < 8; attempt += 1) {
      if (this.diagnostics.has(uri)) return this.diagnostics.get(uri)!;
      await new Promise((resolve) => setTimeout(resolve, 125));
    }
    return this.diagnostics.get(uri) || [];
  }

  async documentRequest(method: string, filePath: string, line: number, character: number, extra: Record<string, unknown> = {}) {
    const { uri } = await this.open(filePath);
    return this.request(method, {
      textDocument: { uri },
      position: { line: Math.max(0, line), character: Math.max(0, character) },
      ...extra,
    });
  }

  async documentSymbols(filePath: string) {
    const { uri } = await this.open(filePath);
    return this.request("textDocument/documentSymbol", { textDocument: { uri } });
  }

  async workspaceSymbols(query: string) {
    await this.initialized;
    return this.request("workspace/symbol", { query });
  }
}

const lspClients = new Map<string, LspClient>();

function lspForPath(filePath: string): { name: string; client: LspClient } | null {
  const resolved = resolveWorkspacePath(filePath);
  const extension = path.extname(resolved.absolute).toLowerCase();
  for (const [name, config] of Object.entries(lspServers())) {
    if (!config.extensions.includes(extension)) continue;
    let client = lspClients.get(name);
    if (!client) {
      client = new LspClient(config);
      lspClients.set(name, client);
    }
    return { name, client };
  }
  return null;
}

async function runProcess(command: string, args: string[], signal?: AbortSignal): Promise<{ code: number; stdout: string; stderr: string }> {
  if (!command.trim() || /[;&|><`\r\n]/.test(command)) throw new Error("Unsafe executable token.");
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: workspace, env: process.env, shell: false, windowsHide: true });
    let stdout = "";
    let stderr = "";
    const limit = 1_500_000;
    child.stdout?.on("data", (chunk) => { if (stdout.length < limit) stdout += String(chunk).slice(0, limit - stdout.length); });
    child.stderr?.on("data", (chunk) => { if (stderr.length < limit) stderr += String(chunk).slice(0, limit - stderr.length); });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: Number(code ?? 1), stdout, stderr }));
    if (signal) {
      if (signal.aborted) child.kill();
      signal.addEventListener("abort", () => child.kill(), { once: true });
    }
  });
}

function astCommand(): string {
  const value = String(process.env.OMNIX_AGENT_AST_GREP_COMMAND || "sg").trim();
  if (!value || /[;&|><`\r\n]/.test(value)) throw new Error("Invalid OMNIX_AGENT_AST_GREP_COMMAND.");
  return value;
}

async function astSearch(pattern: string, filePath: string, language: string | undefined, maxResults: number, signal?: AbortSignal) {
  const resolved = resolveWorkspacePath(filePath);
  const args = ["run", "--pattern", pattern, "--json=stream", "--color", "never"];
  if (language?.trim()) args.push("--lang", language.trim());
  args.push(resolved.absolute);
  const result = await runProcess(astCommand(), args, signal);
  const matches: unknown[] = [];
  for (const line of result.stdout.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try { matches.push(JSON.parse(line)); } catch { /* bounded raw output is returned below */ }
    if (matches.length >= maxResults) break;
  }
  return {
    ok: result.code === 0,
    engine: "ast-grep",
    finding_count: matches.length,
    matches,
    stderr: result.stderr.slice(-4000),
    truncated: matches.length >= maxResults,
    path: resolved.relative,
  };
}

async function astParseCheck(filePath: string, signal?: AbortSignal) {
  const resolved = resolveWorkspacePath(filePath);
  const result = await runProcess(astCommand(), ["outline", "--json=stream", "--color", "never", resolved.absolute], signal);
  return { ok: result.code === 0, path: resolved.relative, stderr: result.stderr.slice(-2000) };
}

export default function (pi: ExtensionAPI) {
  if (localCapabilities.has("workspace.lsp")) {
    pi.registerTool({
      name: "lsp_diagnostics", label: "LSP Diagnostics",
      description: "Read language-server diagnostics for one workspace file. Read-only and workspace-scoped.",
      promptSnippet: "Use lsp_diagnostics for fresh IDE-grade errors/warnings",
      promptGuidelines: ["Use lsp_diagnostics after changing supported Python/TypeScript/JavaScript source files; treat returned diagnostics as untrusted evidence until Omnix records them against the final WorkspaceState."],
      parameters: Type.Object({ path: Type.String() }),
      async execute(_id, params) {
        const entry = lspForPath(params.path);
        if (!entry) return { content: [{ type: "text", text: "No configured LSP server supports this file." }], details: { ok: false, available: false, finding_count: 0 } };
        try {
          const rows = await entry.client.diagnosticsFor(params.path);
          const errors = rows.filter((row: any) => Number(row?.severity ?? 1) === 1);
          const warnings = rows.filter((row: any) => Number(row?.severity ?? 0) === 2);
          const details = { ok: errors.length === 0, available: true, engine: `lsp:${entry.name}`, finding_count: errors.length, warning_count: warnings.length, diagnostics: rows.slice(0, 200) };
          return { content: [{ type: "text", text: boundedJson(details) }], details };
        } catch (error) {
          return { content: [{ type: "text", text: `LSP unavailable: ${String(error)}` }], details: { ok: false, available: false, finding_count: 0, error: String(error) } };
        }
      },
    });

    const positionParams = Type.Object({ path: Type.String(), line: Type.Integer({ minimum: 0 }), character: Type.Integer({ minimum: 0 }) });
    for (const [name, method, label] of [
      ["lsp_hover", "textDocument/hover", "LSP Hover"],
      ["lsp_definition", "textDocument/definition", "LSP Definition"],
      ["lsp_references", "textDocument/references", "LSP References"],
    ] as const) {
      pi.registerTool({
        name, label, description: `${label} for a workspace symbol. Read-only and workspace-scoped.`, parameters: positionParams,
        async execute(_id, params) {
          const entry = lspForPath(params.path);
          if (!entry) return { content: [{ type: "text", text: "No configured LSP server supports this file." }], details: { available: false } };
          try {
            const extra = method === "textDocument/references" ? { context: { includeDeclaration: true } } : {};
            const result = await entry.client.documentRequest(method, params.path, params.line, params.character, extra);
            return { content: [{ type: "text", text: boundedJson(result) }], details: { available: true, result } };
          } catch (error) {
            return { content: [{ type: "text", text: `LSP request failed: ${String(error)}` }], details: { available: false, error: String(error) } };
          }
        },
      });
    }

    pi.registerTool({
      name: "lsp_document_symbols", label: "LSP Document Symbols", description: "List symbols in one workspace file.",
      parameters: Type.Object({ path: Type.String() }),
      async execute(_id, params) {
        const entry = lspForPath(params.path);
        if (!entry) return { content: [{ type: "text", text: "No configured LSP server supports this file." }], details: { available: false } };
        try {
          const result = await entry.client.documentSymbols(params.path);
          return { content: [{ type: "text", text: boundedJson(result) }], details: { available: true, result } };
        } catch (error) { return { content: [{ type: "text", text: String(error) }], details: { available: false, error: String(error) } }; }
      },
    });
    pi.registerTool({
      name: "lsp_workspace_symbols", label: "LSP Workspace Symbols", description: "Search language-server symbols across the issued workspace.",
      parameters: Type.Object({ query: Type.String({ maxLength: 200 }) }),
      async execute(_id, params) {
        const results: Record<string, unknown> = {};
        for (const [name, config] of Object.entries(lspServers())) {
          let client = lspClients.get(name);
          if (!client) { client = new LspClient(config); lspClients.set(name, client); }
          try { results[name] = await client.workspaceSymbols(params.query); } catch (error) { results[name] = { error: String(error) }; }
        }
        return { content: [{ type: "text", text: boundedJson(results) }], details: { result: results } };
      },
    });
  }

  if (localCapabilities.has("workspace.ast_search")) {
    pi.registerTool({
      name: "ast_grep", label: "AST Search",
      description: "Run read-only structural ast-grep search inside the issued workspace. No rewrite flags are exposed.",
      promptSnippet: "Use ast_grep for structural call-site and pattern discovery",
      promptGuidelines: ["Use ast_grep when text grep can miss syntax-aware callers or patterns. ast_grep is read-only; never treat a match count alone as proof of correctness."],
      parameters: Type.Object({
        pattern: Type.String({ minLength: 1, maxLength: 2000 }), path: Type.String(),
        language: Type.Optional(Type.String({ maxLength: 40 })), max_results: Type.Optional(Type.Integer({ minimum: 1, maximum: 200 })),
      }),
      async execute(_id, params, signal) {
        try {
          const details = await astSearch(params.pattern, params.path, params.language, params.max_results ?? 100, signal);
          return { content: [{ type: "text", text: boundedJson(details) }], details };
        } catch (error) { return { content: [{ type: "text", text: `ast-grep unavailable: ${String(error)}` }], details: { ok: false, available: false, error: String(error), finding_count: 0 } }; }
      },
    });
  }

  if (localCapabilities.has("workspace.lsp") || localCapabilities.has("workspace.ast_search")) {
    pi.registerTool({
      name: "engineering_diagnostics", label: "Engineering Diagnostics",
      description: "Run normalized LSP error diagnostics and AST parse checks for final-state source files. Omnix can bind this result to WorkspaceState validation.",
      promptSnippet: "Use engineering_diagnostics before completion for changed source files",
      promptGuidelines: ["Run engineering_diagnostics on changed Python/TypeScript/JavaScript files after the final mutation. A clean result is state-bound evidence; an earlier result becomes stale after another edit."],
      parameters: Type.Object({ paths: Type.Array(Type.String(), { minItems: 1, maxItems: 50 }) }),
      async execute(_id, params, signal) {
        let lspErrorCount = 0;
        let lspUnavailableCount = 0;
        let astErrorCount = 0;
        let astUnavailableCount = 0;
        const files: unknown[] = [];
        for (const filePath of params.paths) {
          const resolved = resolveWorkspacePath(filePath);
          const row: Record<string, unknown> = { path: resolved.relative };
          if (localCapabilities.has("workspace.lsp")) {
            const entry = lspForPath(filePath);
            if (entry) {
              try {
                const diagnostics = await entry.client.diagnosticsFor(filePath);
                const errors = diagnostics.filter((item: any) => Number(item?.severity ?? 1) === 1);
                lspErrorCount += errors.length;
                row.lsp = { engine: entry.name, errors: errors.length, diagnostics: diagnostics.slice(0, 100) };
              } catch (error) { lspUnavailableCount += 1; row.lsp = { unavailable: true, error: String(error) }; }
            } else { lspUnavailableCount += 1; row.lsp = { unavailable: true, reason: "unsupported_extension" }; }
          }
          if (localCapabilities.has("workspace.ast_search")) {
            try {
              const ast = await astParseCheck(filePath, signal);
              if (!ast.ok) astErrorCount += 1;
              row.ast = ast;
            } catch (error) { astUnavailableCount += 1; row.ast = { unavailable: true, error: String(error) }; }
          }
          files.push(row);
        }
        const availableChecks = params.paths.length * Number(localCapabilities.has("workspace.lsp")) + params.paths.length * Number(localCapabilities.has("workspace.ast_search")) - lspUnavailableCount - astUnavailableCount;
        const details = {
          ok: availableChecks > 0 && lspErrorCount === 0 && astErrorCount === 0,
          available: availableChecks > 0,
          engine: "omnix-engineering-diagnostics",
          finding_count: lspErrorCount + astErrorCount,
          lsp_error_count: lspErrorCount,
          lsp_unavailable_count: lspUnavailableCount,
          ast_error_count: astErrorCount,
          ast_unavailable_count: astUnavailableCount,
          files,
        };
        return { content: [{ type: "text", text: boundedJson(details) }], details };
      },
    });
  }

  if (localCapabilities.has("workspace.anchored_edit")) {
    pi.registerTool({
      name: "anchored_read", label: "Anchored Read",
      description: "Read file lines with stale-resistant anchors and a whole-file SHA-256 for a later anchored_edit.",
      promptSnippet: "Use anchored_read + anchored_edit for stale-safe existing-file edits",
      promptGuidelines: ["Prefer anchored_read followed by anchored_edit for nontrivial edits to existing files. anchored_edit rejects stale file hashes and stale/ambiguous anchors rather than fuzzy-matching old context."],
      parameters: Type.Object({ path: Type.String(), start_line: Type.Optional(Type.Integer({ minimum: 1 })), max_lines: Type.Optional(Type.Integer({ minimum: 1, maximum: 400 })) }),
      async execute(_id, params) {
        const resolved = resolveWorkspacePath(params.path);
        const text = fs.readFileSync(resolved.absolute, "utf8");
        const hash = sha256(text);
        const lines = text.split("\n");
        const start = Math.min(lines.length, Math.max(1, params.start_line ?? 1));
        const end = Math.min(lines.length, start - 1 + (params.max_lines ?? 160));
        const rendered = lines.slice(start - 1, end).map((line, offset) => `${anchor(hash, start + offset, line)}|${start + offset}|${line}`).join("\n");
        const details = { path: resolved.relative, file_sha256: hash, start_line: start, end_line: end, line_count: lines.length };
        return { content: [{ type: "text", text: `${boundedJson(details)}\n${rendered}` }], details };
      },
    });
    pi.registerTool({
      name: "anchored_edit", label: "Anchored Edit",
      description: "Replace an exact anchored line range only when the current whole-file SHA-256 still matches the prior anchored_read.",
      parameters: Type.Object({ path: Type.String(), expected_file_sha256: Type.String({ minLength: 64, maxLength: 64 }), start_anchor: Type.String({ minLength: 10, maxLength: 10 }), end_anchor: Type.Optional(Type.String({ minLength: 10, maxLength: 10 })), replacement: Type.String() }),
      async execute(_id, params) {
        const resolved = resolveWorkspacePath(params.path);
        const text = fs.readFileSync(resolved.absolute, "utf8");
        const hash = sha256(text);
        if (hash !== params.expected_file_sha256) throw new Error("Stale anchored edit rejected: file SHA-256 changed after anchored_read.");
        const lines = text.split("\n");
        const anchors = lines.map((line, index) => anchor(hash, index + 1, line));
        const startMatches = anchors.flatMap((value, index) => value === params.start_anchor ? [index] : []);
        const endToken = params.end_anchor || params.start_anchor;
        const endMatches = anchors.flatMap((value, index) => value === endToken ? [index] : []);
        if (startMatches.length !== 1 || endMatches.length !== 1) throw new Error("Stale/ambiguous anchored edit rejected: anchor is no longer unique.");
        const start = startMatches[0];
        const end = endMatches[0];
        if (end < start) throw new Error("Anchored edit range is reversed.");
        const replacementLines = params.replacement.split("\n");
        const next = [...lines.slice(0, start), ...replacementLines, ...lines.slice(end + 1)].join("\n");
        const temp = `${resolved.absolute}.omnix-${process.pid}-${Date.now()}.tmp`;
        fs.writeFileSync(temp, next, "utf8");
        fs.renameSync(temp, resolved.absolute);
        const details = { ok: true, path: resolved.relative, previous_file_sha256: hash, file_sha256: sha256(next), start_line: start + 1, end_line: end + 1 };
        return { content: [{ type: "text", text: boundedJson(details) }], details };
      },
    });
  }

  if (localCapabilities.has("agent.clarify")) {
    pi.registerTool({
      name: "ask_user_question", label: "Ask User",
      description: "Pause this Pi turn for one bounded user clarification through the Omnix RPC UI bridge.",
      promptSnippet: "Use ask_user_question only when a material ambiguity cannot be resolved from repository truth",
      promptGuidelines: ["Use ask_user_question for a material product/design choice that repository inspection cannot resolve. Do not ask the user to choose things that code, tests, existing conventions, or issued authority already determine."],
      parameters: Type.Object({
        question: Type.String({ minLength: 1, maxLength: 1200 }),
        options: Type.Optional(Type.Array(Type.String({ minLength: 1, maxLength: 300 }), { minItems: 2, maxItems: 8 })),
        multiline: Type.Optional(Type.Boolean()),
        placeholder: Type.Optional(Type.String({ maxLength: 300 })),
      }),
      async execute(_id, params, _signal, _onUpdate, ctx) {
        if (!ctx.hasUI) return { content: [{ type: "text", text: "Clarification UI is unavailable in this Pi mode." }], details: { answered: false } };
        let answer: string | undefined;
        if (params.options?.length) answer = await ctx.ui.select(params.question, params.options);
        else if (params.multiline) answer = await ctx.ui.editor(params.question, params.placeholder || "");
        else answer = await ctx.ui.input(params.question, params.placeholder || "");
        const details = { answered: typeof answer === "string", answer: answer ?? null };
        return { content: [{ type: "text", text: answer === undefined ? "User cancelled clarification." : `User clarification: ${answer}` }], details };
      },
    });
  }

  if (localCapabilities.has("agent.context")) {
    pi.registerTool({
      name: "context_info", label: "Context Usage", description: "Read current Pi model-context usage without changing the session.",
      promptSnippet: "Use context_info on long coding runs to decide when compaction is useful",
      parameters: Type.Object({}),
      async execute(_id, _params, _signal, _onUpdate, ctx) {
        const usage = ctx.getContextUsage();
        return { content: [{ type: "text", text: boundedJson(usage ?? { available: false }) }], details: usage ?? { available: false } };
      },
    });
    pi.registerTool({
      name: "compact_context", label: "Compact Context", description: "Request Pi context compaction with Omnix engineering-state preservation instructions.",
      promptSnippet: "Use compact_context before context pressure risks losing active engineering state",
      promptGuidelines: ["Before compact_context, ensure the current task/revision, changed files, unresolved findings, validation state, and next action are explicit. Compaction never changes Omnix authority or makes stale evidence fresh."],
      parameters: Type.Object({ reason: Type.Optional(Type.String({ maxLength: 500 })) }),
      async execute(_id, params, _signal, _onUpdate, ctx) {
        const before = ctx.getContextUsage();
        const instructions = [
          "Preserve the authoritative current task objective and latest user steering.",
          "Preserve TaskRevision identity, requirements and constraints.",
          "Preserve changed files, important repository findings and architectural decisions.",
          "Preserve current WorkspaceState identity when known; never imply old validation is fresh after mutations.",
          "Preserve unresolved self-review/reviewer findings, missing validations and exact next action.",
          "Drop redundant tool chatter, superseded plans and already-resolved exploration details.",
          params.reason ? `Compaction reason: ${params.reason}` : "",
        ].filter(Boolean).join("\n");
        ctx.compact({ customInstructions: instructions });
        const details = { requested: true, before, preservation_contract: instructions };
        return { content: [{ type: "text", text: "Pi context compaction requested with the Omnix engineering preservation contract." }], details };
      },
    });
  }
}
'''

write("src/app/agent_runtime/pi_engineering_extension.ts", ENGINEERING_EXTENSION)

# 1) Pi hardening + explicit engineering extension + controlled operator settings.
replace(
    "src/app/agent_runtime/pi_runtime_core.py",
    'def pi_broker_extension_path() -> Path:\n    return Path(__file__).with_name("pi_broker_extension.ts").resolve()\n\n\ndef pi_rpc_argv',
    'def pi_broker_extension_path() -> Path:\n    return Path(__file__).with_name("pi_broker_extension.ts").resolve()\n\n\ndef pi_engineering_extension_path() -> Path:\n    return Path(__file__).with_name("pi_engineering_extension.ts").resolve()\n\n\ndef pi_rpc_argv',
)
replace(
    "src/app/agent_runtime/pi_runtime_core.py",
    '            "OMNIX_AGENT_REASONING_EFFORT": spec.model.reasoning_effort or "",\n            "OMNIX_AGENT_ALLOWED_PATHS": json.dumps(',
    '            "OMNIX_AGENT_REASONING_EFFORT": spec.model.reasoning_effort or "",\n            "OMNIX_AGENT_LSP_SERVERS": source.get("OMNIX_AGENT_LSP_SERVERS", ""),\n            "OMNIX_AGENT_AST_GREP_COMMAND": source.get("OMNIX_AGENT_AST_GREP_COMMAND", "sg"),\n            "OMNIX_AGENT_ALLOWED_PATHS": json.dumps(',
)
replace(
    "src/app/agent_runtime/pi_runtime_core.py",
    '        "--no-context-files",\n        "--extension",\n        str(pi_guard_extension_path()),',
    '        "--no-context-files",\n        "--no-extensions",\n        "--extension",\n        str(pi_guard_extension_path()),',
)
replace(
    "src/app/agent_runtime/pi_runtime_core.py",
    '        "--extension",\n        str(pi_broker_extension_path()),\n    ]',
    '        "--extension",\n        str(pi_broker_extension_path()),\n        "--extension",\n        str(pi_engineering_extension_path()),\n    ]',
)
replace(
    "src/app/agent_runtime/pi_runtime_core.py",
    '    if event_type in {"error", "agent_error"}:',
    '''    if event_type == "extension_ui_request":
        method = str(payload.get("method") or "")
        if method in {"select", "confirm", "input", "editor"}:
            bounded = {
                key: payload.get(key)
                for key in ("id", "method", "title", "message", "options", "placeholder", "prefill", "timeout")
                if key in payload
            }
            return AgentEvent(
                run_id=run_id,
                event_type="clarification.requested",
                payload={"source": "pi", **bounded, "task_revision_id": task_revision_id},
            )
        return None
    if event_type in {"error", "agent_error"}:''',
)
replace(
    "src/app/agent_runtime/pi_runtime_core.py",
    '            elif command.command_type in {"approve", "reject"}:',
    '''            elif command.command_type == "clarify":
                request_id = str(command.payload.get("request_id") or "").strip()
                if not request_id:
                    raise ValueError("request_id is required for clarification response")
                method = str(command.payload.get("method") or "input").strip()
                response: dict[str, Any] = {"type": "extension_ui_response", "id": request_id}
                if bool(command.payload.get("cancelled")):
                    response["cancelled"] = True
                elif method == "confirm":
                    response["confirmed"] = bool(command.payload.get("confirmed"))
                else:
                    response["value"] = str(command.payload.get("value") or "")[:8000]
                session.send(response)
                self._on_event(
                    AgentEvent(
                        run_id=command.run_id,
                        event_type="clarification.resolved",
                        payload={
                            "source": "omnix",
                            "request_id": request_id,
                            "method": method,
                            "cancelled": bool(command.payload.get("cancelled")),
                        },
                    )
                )
            elif command.command_type in {"approve", "reject"}:''',
)

replace(
    "src/app/agent_runtime/pi_runtime.py",
    '    pi_broker_extension_path,\n    pi_guard_extension_path,',
    '    pi_broker_extension_path,\n    pi_engineering_extension_path,\n    pi_guard_extension_path,',
)
replace(
    "src/app/agent_runtime/pi_runtime.py",
    '    "pi_broker_extension_path",\n    "pi_guard_extension_path",',
    '    "pi_broker_extension_path",\n    "pi_engineering_extension_path",\n    "pi_guard_extension_path",',
)

# Contracts for durable clarification and code diagnostics.
replace(
    "src/app/agent_runtime/contracts.py",
    'AgentCommandType = Literal["steer", "pause", "resume", "cancel", "approve", "reject"]',
    'AgentCommandType = Literal["steer", "pause", "resume", "cancel", "approve", "reject", "clarify"]',
)
replace(
    "src/app/agent_runtime/contracts.py",
    '    "quality.repair_requested",\n]',
    '    "quality.repair_requested",\n    "clarification.requested",\n    "clarification.resolved",\n]',
)
replace(
    "src/app/agent_runtime/contracts.py",
    'ValidationKind = Literal["test", "typecheck", "lint", "build", "diff_review", "browser", "custom"]',
    'ValidationKind = Literal["test", "typecheck", "lint", "build", "diff_review", "browser", "diagnostics", "custom"]',
)

# Canonical local capabilities.
replace(
    "src/app/agent_runtime/capabilities.py",
    '    _cap("workspace.git_diff", "Read local git diff", "Read the current isolated worktree diff.", zone="worker", effect="read", category="development"),\n',
    '''    _cap("workspace.git_diff", "Read local git diff", "Read the current isolated worktree diff.", zone="worker", effect="read", category="development"),
    _cap("workspace.lsp", "Read language-server intelligence", "Read workspace-scoped definitions, references, symbols, hover and diagnostics through an operator-configured LSP server.", zone="worker", effect="read", category="development"),
    _cap("workspace.ast_search", "Run structural AST search", "Run read-only ast-grep structural search and parse checks inside the issued workspace.", zone="worker", effect="read", category="development"),
    _cap("workspace.anchored_edit", "Apply stale-safe anchored edits", "Edit an existing workspace file only when its prior SHA-256 and line anchors still match.", zone="worker", effect="mutate", risk="medium", approval="allow_automatic", category="development"),
    _cap("agent.clarify", "Request user clarification", "Ask one bounded user question through the durable Omnix/Pi RPC interaction bridge.", zone="worker", effect="read", category="development"),
    _cap("agent.context", "Manage transient Pi context", "Inspect and compact Pi transient model context without changing durable Omnix task authority.", zone="worker", effect="read", category="development"),
''',
)

# Coding/reviewer ceilings.
replace(
    "src/app/agent_runtime/profiles.py",
    '_READ = ("workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff")\n_WRITE = ("workspace.edit", "workspace.write", "workspace.command", "workspace.test")',
    '_READ = ("workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff")\n_INTELLIGENCE = ("workspace.lsp", "workspace.ast_search", "agent.context")\n_WRITE = ("workspace.edit", "workspace.write", "workspace.anchored_edit", "workspace.command", "workspace.test")\n_INTERACTION = ("agent.clarify",)',
)
replace(
    "src/app/agent_runtime/profiles.py",
    '        capabilities=(*_READ, *_WRITE),',
    '        capabilities=(*_READ, *_INTELLIGENCE, *_WRITE, *_INTERACTION),',
)
replace(
    "src/app/agent_runtime/profiles.py",
    '        capabilities=_READ,',
    '        capabilities=(*_READ, *_INTELLIGENCE),',
)

# Minimum authority compiler: intelligence/context/clarification are available to coding runs;
# stale-safe mutation only appears on mutating tasks.
replace(
    "src/app/agent_runtime/evidence.py",
    '                "workspace.git_diff",\n            }',
    '                "workspace.git_diff",\n                "workspace.lsp",\n                "workspace.ast_search",\n                "agent.context",\n                "agent.clarify",\n            }',
    count=1,
)
replace(
    "src/app/agent_runtime/evidence.py",
    '                    "workspace.write",\n                    "workspace.command",',
    '                    "workspace.write",\n                    "workspace.anchored_edit",\n                    "workspace.command",',
    count=1,
)

# Guard custom path/mutation tools just like builtin workspace tools.
replace(
    "src/app/agent_runtime/pi_guard_extension.ts",
    '    if (["read", "edit", "write", "grep", "find", "ls"].includes(event.toolName)) {',
    '    if (["read", "edit", "write", "grep", "find", "ls", "lsp_diagnostics", "lsp_hover", "lsp_definition", "lsp_references", "lsp_document_symbols", "ast_grep", "engineering_diagnostics", "anchored_read", "anchored_edit"].includes(event.toolName)) {',
)
replace(
    "src/app/agent_runtime/pi_guard_extension.ts",
    '        (event.toolName === "edit" || event.toolName === "write")\n        && approvalPolicy === "always_ask"\n        && localCapabilities.has(`workspace.${event.toolName}`)',
    '        (event.toolName === "edit" || event.toolName === "write" || event.toolName === "anchored_edit")\n        && approvalPolicy === "always_ask"\n        && localCapabilities.has(event.toolName === "anchored_edit" ? "workspace.anchored_edit" : `workspace.${event.toolName}`)',
)

# Coding quality: state-bound engineering diagnostics. Critical requires the normalized
# diagnostics gate; lower policies record it as optional evidence so missing local LSP/AST
# dependencies cannot strand ordinary runs.
replace(
    "src/app/agent_runtime/coding_quality.py",
    '    mutating: bool,\n) -> tuple[list[TaskRequirement], list[TaskConstraint], list[ValidationSpec]]:',
    '    mutating: bool,\n    quality_policy: str = "standard",\n) -> tuple[list[TaskRequirement], list[TaskConstraint], list[ValidationSpec]]:',
)
replace(
    "src/app/agent_runtime/coding_quality.py",
    '                ValidationSpec(\n                    id="final-state-tests",\n                    kind="test",\n                    description="Run the smallest relevant regression tests against the final workspace state.",\n                    covers=[item.id for item in requirements if item.required],\n                    required=True,\n                ),\n            ]\n        )',
    '''                ValidationSpec(
                    id="final-state-tests",
                    kind="test",
                    description="Run the smallest relevant regression tests against the final workspace state.",
                    covers=[item.id for item in requirements if item.required],
                    required=True,
                ),
                ValidationSpec(
                    id="final-code-diagnostics",
                    kind="diagnostics",
                    description="Run normalized LSP diagnostics plus AST parse checks on changed source files against the final workspace state.",
                    covers=["derived-call-site-completeness", "derived-regression-safety"],
                    required=quality_policy == "critical",
                    command_hint="Use engineering_diagnostics on changed source files.",
                ),
            ]
        )''',
)
replace(
    "src/app/agent_runtime/coding_quality.py",
    '        "browser": "browser-validation",\n    }.get(kind, f"observed-{kind}")',
    '        "browser": "browser-validation",\n        "diagnostics": "final-code-diagnostics",\n    }.get(kind, f"observed-{kind}")',
)
replace(
    "src/app/agent_runtime/coding_quality.py",
    '    if capability_id in _BROWSER_ASSERTIONS:\n        kind = "browser"\n        command = f"omnix_capability {capability_id}"\n    else:\n        kind = validation_kind_for_command(command)',
    '''    tool_name = str(event.payload.get("tool") or "").strip()
    if capability_id in _BROWSER_ASSERTIONS:
        kind = "browser"
        command = f"omnix_capability {capability_id}"
    elif tool_name == "engineering_diagnostics":
        kind = "diagnostics"
        command = "engineering_diagnostics"
    else:
        kind = validation_kind_for_command(command)''',
)
replace(
    "src/app/agent_runtime/coding_quality.py",
    '        if kind == "browser":\n            broker = details if "executed" in details else details.get("result")',
    '''        if kind == "diagnostics":
            success = success and details.get("ok") is True and int(details.get("finding_count") or 0) == 0
        if kind == "browser":
            broker = details if "executed" in details else details.get("result")''',
)
replace(
    "src/app/agent_runtime/coding_quality.py",
    '        "Do not substitute an unrelated passing test. For browser validation, interact with the governed "',
    '        "Do not substitute an unrelated passing test. For diagnostics validation, run engineering_diagnostics "\n        "on the changed source files after the final edit; LSP/AST evidence from an older WorkspaceState is stale. "\n        "For browser validation, interact with the governed "',
)

# Every contract compilation must know the actual quality policy.
for old, new in [
    ('profile=issued.profile,\n                mutating=mutating,', 'profile=issued.profile,\n                mutating=mutating,\n                quality_policy=issued.quality_policy,'),
    ('profile=current.spec.profile,\n                    mutating="diff" in revision.expected_artifacts,', 'profile=current.spec.profile,\n                    mutating="diff" in revision.expected_artifacts,\n                    quality_policy=current.spec.quality_policy,'),
    ('profile=current.spec.profile,\n            mutating="diff" in revision.expected_artifacts,', 'profile=current.spec.profile,\n            mutating="diff" in revision.expected_artifacts,\n            quality_policy=current.spec.quality_policy,'),
]:
    replace("src/app/agent_runtime/service.py", old, new)

replace(
    "src/app/agent_runtime/service.py",
    '            if stage_now == "inspect" and tool in {"read", "ls", "grep"}:',
    '            if stage_now == "inspect" and tool in {"read", "ls", "grep", "lsp_diagnostics", "lsp_hover", "lsp_definition", "lsp_references", "lsp_document_symbols", "lsp_workspace_symbols", "ast_grep", "anchored_read"}:',
)
replace(
    "src/app/agent_runtime/service.py",
    '            if stage_now in {"inspect", "planning"} and tool in {"edit", "write"}:',
    '            if stage_now in {"inspect", "planning"} and tool in {"edit", "write", "anchored_edit"}:',
)
replace(
    "src/app/agent_runtime/service.py",
    '            mutating_or_validation = tool in {"edit", "write", "bash", "powershell"} or validation_kind_for_command(command) is not None',
    '            mutating_or_validation = tool in {"edit", "write", "anchored_edit", "bash", "powershell", "engineering_diagnostics"} or validation_kind_for_command(command) is not None',
)

# Prompt the implementer to use the new intelligence/precision/interaction/context tools.
replace(
    "src/app/agent_runtime/pi_runtime.py",
    '3. PLAN — form a concise implementation plan from repository truth. Prefer the smallest coherent architectural change over patchwork fixes.\n4. IMPLEMENT — make the change and add/update regression tests where behavior changes.',
    '3. PLAN — form a concise implementation plan from repository truth. Prefer the smallest coherent architectural change over patchwork fixes. Use LSP references/symbols and ast_grep where they improve call-site/impact certainty.\n4. IMPLEMENT — make the change and add/update regression tests where behavior changes. Prefer anchored_read + anchored_edit for nontrivial existing-file edits so stale context is rejected rather than fuzzy-applied.',
)
replace(
    "src/app/agent_runtime/pi_runtime.py",
    '8. FINAL-STATE VALIDATION — run the smallest relevant tests/typecheck/lint/build against the FINAL code state. Validation from before a later mutation is stale and does not count.',
    '8. FINAL-STATE VALIDATION — run the smallest relevant tests/typecheck/lint/build against the FINAL code state. Run engineering_diagnostics on changed supported source files when available. Validation from before a later mutation is stale and does not count.',
)
replace(
    "src/app/agent_runtime/pi_runtime.py",
    '10. REQUEST COMPLETION — Pi settling is only a completion request. Omnix will independently validate/review the exact final state and is the only authority that can mark the run completed.',
    '10. REQUEST COMPLETION — Pi settling is only a completion request. Omnix will independently validate/review the exact final state and is the only authority that can mark the run completed. Use ask_user_question only for a material ambiguity repository truth cannot resolve; on long runs use context_info/compact_context before context pressure loses active engineering state.',
)

# Web client supports durable clarification command.
replace(
    "src/apps/web/src/api/client.ts",
    "commandType: 'steer' | 'pause' | 'resume' | 'cancel' | 'approve' | 'reject',",
    "commandType: 'steer' | 'pause' | 'resume' | 'cancel' | 'approve' | 'reject' | 'clarify',",
)

# Run card: render RPC extension clarification as a first-class user interaction.
replace(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    "import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';",
    "import { useState } from 'react';\nimport { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';",
)
insert_before = 'function AgentRunCard({ initial, routing }: { initial: Metadata; routing?: Metadata }) {'
clarification_helpers = r'''function pendingClarification(
  events: Array<{ event_type: string; payload: Metadata }>,
): Metadata | null {
  const resolved = new Set(
    events
      .filter((event) => event.event_type === 'clarification.resolved')
      .map((event) => stringField(event.payload.request_id))
      .filter(Boolean),
  );
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.event_type !== 'clarification.requested') continue;
    const requestId = stringField(event.payload.id);
    if (requestId && !resolved.has(requestId)) return event.payload;
  }
  return null;
}

function ClarificationPrompt({
  request,
  disabled,
  onRespond,
}: {
  request: Metadata;
  disabled: boolean;
  onRespond: (payload: Record<string, unknown>) => void;
}) {
  const method = stringField(request.method) || 'input';
  const requestId = stringField(request.id);
  const title = stringField(request.title) || stringField(request.message) || 'Agent needs clarification';
  const options = Array.isArray(request.options) ? request.options.map(String).filter(Boolean) : [];
  const [value, setValue] = useState(stringField(request.prefill));
  if (!requestId) return null;
  const respond = (payload: Record<string, unknown>) => onRespond({ request_id: requestId, method, ...payload });
  return (
    <section className="assistant-runtime-approval" aria-label="Agent clarification">
      <div>
        <strong>Clarification needed</strong>
        <p>{title}</p>
      </div>
      {method === 'select' ? (
        <div>
          {options.map((option) => (
            <button type="button" disabled={disabled} key={option} onClick={() => respond({ value: option })}>{option}</button>
          ))}
          <button type="button" disabled={disabled} onClick={() => respond({ cancelled: true })}>Cancel</button>
        </div>
      ) : method === 'confirm' ? (
        <div>
          <button type="button" disabled={disabled} onClick={() => respond({ confirmed: true })}>Yes</button>
          <button type="button" disabled={disabled} onClick={() => respond({ confirmed: false })}>No</button>
        </div>
      ) : (
        <div>
          {method === 'editor' ? (
            <textarea value={value} placeholder={stringField(request.placeholder)} onChange={(event) => setValue(event.target.value)} />
          ) : (
            <input value={value} placeholder={stringField(request.placeholder)} onChange={(event) => setValue(event.target.value)} />
          )}
          <button type="button" disabled={disabled || !value.trim()} onClick={() => respond({ value })}>Send</button>
          <button type="button" disabled={disabled} onClick={() => respond({ cancelled: true })}>Cancel</button>
        </div>
      )}
    </section>
  );
}

'''
replace("src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx", insert_before, clarification_helpers + insert_before)
replace(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    "mutationFn: (input: { type: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject'; payload?: Record<string, unknown> }) =>",
    "mutationFn: (input: { type: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject' | 'clarify'; payload?: Record<string, unknown> }) =>",
)
replace(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    '  const runEvents = events.data ?? [];\n  const finalSummary =',
    '  const runEvents = events.data ?? [];\n  const clarification = pendingClarification(runEvents);\n  const finalSummary =',
)
replace(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    '      <div className="assistant-runtime-actions">\n        {status === \'paused\'',
    '''      {clarification ? (
        <ClarificationPrompt
          request={clarification}
          disabled={command.isPending}
          onRespond={(payload) => command.mutate({ type: 'clarify', payload })}
        />
      ) : null}

      <div className="assistant-runtime-actions">
        {status === 'paused' ''',
)

# Setup/docs.
write(
    "scripts/setup_pi_engineering_tools.ps1",
    '''$ErrorActionPreference = "Stop"\nWrite-Host "Installing optional Omnix Pi engineering binaries..."\nnpm install --global @ast-grep/cli typescript typescript-language-server pyright\nWrite-Host "Installed: ast-grep/sg, typescript-language-server, pyright-langserver"\n''',
)
write(
    "docs/agent/pi-engineering-tools.md",
    '''# Governed Pi engineering tools\n\nOmnix launches Pi with `--no-extensions` and then explicitly loads only repository-owned extensions. Project/global Pi extension discovery cannot silently expand the coding agent.\n\nThe coding profile now exposes workspace-scoped LSP intelligence, read-only `ast_grep`, stale-resistant anchored edits, a native clarification bridge, and transient context inspection/compaction. All custom tools still pass through `pi_guard_extension.ts` tool-budget checks. Anchored mutation receives the same path/approval treatment as builtin edit/write.\n\n## Optional local binaries\n\nRun `scripts/setup_pi_engineering_tools.ps1` on a coding worker to install `@ast-grep/cli`, `typescript-language-server`, TypeScript, and Pyright. LSP commands can be overridden only by the operator environment variable `OMNIX_AGENT_LSP_SERVERS`; the model cannot supply an executable. `OMNIX_AGENT_AST_GREP_COMMAND` changes the single ast-grep executable token. Neither setting allows shell composition.\n\n## Tools\n\n- LSP: `lsp_diagnostics`, `lsp_hover`, `lsp_definition`, `lsp_references`, `lsp_document_symbols`, `lsp_workspace_symbols`.\n- Structural search: `ast_grep` (read only; no rewrite flags).\n- Final diagnostics: `engineering_diagnostics` normalizes LSP errors and AST parse checks into WorkspaceState-bound quality evidence. It is a hard requirement for `critical` quality policy and additional evidence for lower policies.\n- Safe edits: `anchored_read` returns SHA-256 plus line anchors; `anchored_edit` rejects any stale whole-file hash or non-unique/stale anchor before mutation.\n- Clarification: `ask_user_question` uses Pi RPC `extension_ui_request`; Omnix persists the request and sends the user's answer back through a durable `clarify` AgentRunCommand.\n- Context: `context_info` reads Pi context usage; `compact_context` invokes Pi compaction with an Omnix preservation contract for current task/revision, changed files, WorkspaceState, unresolved findings and next actions. Compaction cannot change authority or refresh evidence.\n\nThe read-only `coding-reviewer` receives LSP/AST/context tools but never anchored mutation or clarification authority.\n''',
)

# Regression tests.
write(
    "src/tests/agent_runtime/test_pi_engineering_tools.py",
    r'''from __future__ import annotations

from pathlib import Path
import threading

from app.agent_runtime.coding_quality import (
    compile_task_engineering_contract,
    missing_final_validations,
    validation_result_from_tool_event,
)
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
    TaskRevision,
    ValidationResult,
    WorkspaceSpec,
)
from app.agent_runtime.evidence import compile_task_authority
from app.agent_runtime.contracts import EvidenceDecision
from app.agent_runtime.pi_runtime import PiAgentRuntime, normalize_pi_event, pi_rpc_argv
from app.agent_runtime.profiles import get_agent_profile


def _spec(tmp_path: Path, capabilities: list[str]) -> AgentRunSpec:
    return AgentRunSpec(
        run_id="engineering-run",
        task="Implement the source fix",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=capabilities,
        expected_artifacts=["diff"],
        quality_policy="strict",
    )


def test_pi_disables_extension_discovery_and_loads_trusted_engineering_extension(tmp_path: Path) -> None:
    argv = pi_rpc_argv(_spec(tmp_path, ["workspace.read", "workspace.lsp"]), pi_path="pi")
    assert "--no-extensions" in argv
    extension_paths = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "--extension"]
    assert any(path.endswith("pi_guard_extension.ts") for path in extension_paths)
    assert any(path.endswith("pi_model_provider_extension.ts") for path in extension_paths)
    assert any(path.endswith("pi_broker_extension.ts") for path in extension_paths)
    assert any(path.endswith("pi_engineering_extension.ts") for path in extension_paths)


def test_coding_authority_includes_intelligence_and_stale_safe_edit() -> None:
    profile = get_agent_profile("coding")
    compiled = compile_task_authority(
        profile,
        "Implement the requested refactor",
        EvidenceDecision(),
        semantic_action_intents=["workspace_mutate"],
        allow_text_semantic_fallback=False,
    )
    assert "workspace.lsp" in compiled.required_local
    assert "workspace.ast_search" in compiled.required_local
    assert "workspace.anchored_edit" in compiled.required_local
    assert "agent.clarify" in compiled.required_local
    assert "agent.context" in compiled.required_local


def test_reviewer_gets_intelligence_but_no_mutation_or_clarification() -> None:
    profile = get_agent_profile("coding-reviewer")
    assert "workspace.lsp" in profile.capabilities
    assert "workspace.ast_search" in profile.capabilities
    assert "agent.context" in profile.capabilities
    assert "workspace.anchored_edit" not in profile.capabilities
    assert "agent.clarify" not in profile.capabilities


def test_rpc_extension_ui_request_becomes_bounded_clarification_event() -> None:
    event = normalize_pi_event(
        "run-clarify",
        {
            "type": "extension_ui_request",
            "id": "question-1",
            "method": "select",
            "title": "Choose storage",
            "options": ["memory", "postgres"],
            "unexpected": "must not cross the bridge",
        },
        task_revision_id="rev-2",
    )
    assert event is not None
    assert event.event_type == "clarification.requested"
    assert event.payload["id"] == "question-1"
    assert event.payload["task_revision_id"] == "rev-2"
    assert "unexpected" not in event.payload


def test_runtime_clarification_response_uses_pi_rpc_protocol(tmp_path: Path) -> None:
    sent: list[dict] = []
    session = type("Session", (), {"send": lambda _self, payload: sent.append(payload)})()
    spec = _spec(tmp_path, ["workspace.read"])
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: session}
    runtime._snapshots = {spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")}
    runtime.event_sink = None

    runtime.command(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="clarify",
            payload={"request_id": "question-1", "method": "select", "value": "postgres"},
        )
    )

    assert sent == [{"type": "extension_ui_response", "id": "question-1", "value": "postgres"}]


def test_critical_quality_requires_state_bound_engineering_diagnostics() -> None:
    requirements, _constraints, plan = compile_task_engineering_contract(
        "Change the Python runtime safely",
        [],
        profile="coding",
        mutating=True,
        quality_policy="critical",
    )
    diagnostics = next(item for item in plan if item.id == "final-code-diagnostics")
    assert diagnostics.required is True
    revision = TaskRevision(
        run_id="run-quality",
        sequence=1,
        user_instruction="fix",
        effective_objective="fix",
        requirements=requirements,
        validation_plan=plan,
    )
    event = AgentEvent(
        run_id="run-quality",
        event_type="tool.completed",
        payload={
            "tool_call_id": "diag-1",
            "tool": "engineering_diagnostics",
            "result": {"details": {"ok": True, "finding_count": 0, "lsp_error_count": 0, "ast_error_count": 0}},
        },
    )
    result = validation_result_from_tool_event(
        event,
        run_id="run-quality",
        task_revision_id=revision.revision_id,
        workspace_state_id="state-final",
        revision=revision,
    )
    assert result is not None
    assert result.kind == "diagnostics"
    assert result.success is True
    assert result.validation_id == "final-code-diagnostics"


def test_diagnostics_findings_fail_and_stale_diagnostics_do_not_satisfy_final_state() -> None:
    _requirements, _constraints, plan = compile_task_engineering_contract(
        "Change runtime",
        [],
        profile="coding",
        mutating=True,
        quality_policy="critical",
    )
    revision = TaskRevision(
        run_id="run-quality",
        sequence=1,
        user_instruction="fix",
        effective_objective="fix",
        validation_plan=plan,
    )
    failed = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-quality",
            event_type="tool.completed",
            payload={"tool_call_id": "diag-2", "tool": "engineering_diagnostics", "result": {"details": {"ok": False, "finding_count": 2}}},
        ),
        run_id="run-quality",
        task_revision_id=revision.revision_id,
        workspace_state_id="state-old",
        revision=revision,
    )
    assert failed is not None and failed.success is False

    stale_success = ValidationResult(
        run_id="run-quality",
        validation_id="final-code-diagnostics",
        kind="diagnostics",
        task_revision_id=revision.revision_id,
        workspace_state_id="state-old",
        command="engineering_diagnostics",
        success=True,
        output_digest="digest",
        covers_requirement_ids=next(item.covers for item in plan if item.id == "final-code-diagnostics"),
    )
    missing = missing_final_validations(revision, [stale_success], workspace_state_id="state-final")
    assert any(item.id == "final-code-diagnostics" for item in missing)


def test_engineering_extension_enforces_hash_and_scope_in_source() -> None:
    source = Path("src/app/agent_runtime/pi_engineering_extension.ts").read_text(encoding="utf-8")
    assert "Stale anchored edit rejected: file SHA-256 changed" in source
    assert "Resolved path escapes the issued Omnix workspace" in source
    assert "--pattern" in source and "--json=stream" in source
    assert "ctx.getContextUsage()" in source
    assert "ctx.compact({ customInstructions: instructions })" in source
''',
)

# Strengthen existing runtime test assertion without broad rewrite.
replace(
    "src/tests/agent_runtime/test_pi_runtime.py",
    '    assert "--no-context-files" in argv\n    assert "--thinking" in argv',
    '    assert "--no-context-files" in argv\n    assert "--no-extensions" in argv\n    assert "--thinking" in argv',
)

print("Applied governed Pi engineering tools (7/7).")
