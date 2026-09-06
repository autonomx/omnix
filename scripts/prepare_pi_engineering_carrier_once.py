from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {text.count(old)}: {old[:120]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def prepare() -> None:
    path = ROOT / "scripts/apply_pi_engineering_tools_once.py"
    text = path.read_text(encoding="utf-8")
    old = '''replace(
    "src/app/agent_runtime/evidence.py",
    '                "workspace.git_diff",\\n            }',
    '                "workspace.git_diff",\\n                "workspace.lsp",\\n                "workspace.ast_search",\\n                "agent.context",\\n                "agent.clarify",\\n            }',
    count=1,
)'''
    new = '''replace(
    "src/app/agent_runtime/evidence.py",
    '    if profile.id == "coding":\\n        read_caps = [\\n            capability\\n            for capability in profile.capabilities\\n            if capability in {\\n                "workspace.read",\\n                "workspace.list",\\n                "workspace.search",\\n                "workspace.git_status",\\n                "workspace.git_diff",\\n            }\\n        ]',
    '    if profile.id == "coding":\\n        read_caps = [\\n            capability\\n            for capability in profile.capabilities\\n            if capability in {\\n                "workspace.read",\\n                "workspace.list",\\n                "workspace.search",\\n                "workspace.git_status",\\n                "workspace.git_diff",\\n                "workspace.lsp",\\n                "workspace.ast_search",\\n                "agent.context",\\n                "agent.clarify",\\n            }\\n        ]',
)'''
    if text.count(old) != 1:
        raise RuntimeError(f"expected one coding authority patch, found {text.count(old)}")
    text = text.replace(old, new)
    replacements = {
        'source.get("OMNIX_AGENT_AST_GREP_COMMAND", "sg")': 'source.get("OMNIX_AGENT_AST_GREP_COMMAND", "ast-grep")',
        'process.env.OMNIX_AGENT_AST_GREP_COMMAND || "sg"': 'process.env.OMNIX_AGENT_AST_GREP_COMMAND || "ast-grep"',
        'Installed: ast-grep/sg, typescript-language-server, pyright-langserver': 'Installed: ast-grep, typescript-language-server, pyright-langserver',
    }
    for before, after in replacements.items():
        if text.count(before) != 1:
            raise RuntimeError(f"expected one ast-grep default occurrence: {before!r}, got {text.count(before)}")
        text = text.replace(before, after)
    path.write_text(text, encoding="utf-8")


def _harden_engineering_extension() -> None:
    extension = ROOT / "src/app/agent_runtime/pi_engineering_extension.ts"
    text = extension.read_text(encoding="utf-8")

    old_servers = '''  typescript: {
    command: "typescript-language-server",
    args: ["--stdio"],
    extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
    language_id: "typescript",
  },
  python: {'''
    new_servers = '''  typescript: {
    command: "typescript-language-server",
    args: ["--stdio"],
    extensions: [".ts", ".tsx"],
    language_id: "typescript",
  },
  javascript: {
    command: "typescript-language-server",
    args: ["--stdio"],
    extensions: [".js", ".jsx", ".mjs", ".cjs"],
    language_id: "javascript",
  },
  python: {'''
    if text.count(old_servers) != 1:
        raise RuntimeError("unexpected default LSP server block")
    text = text.replace(old_servers, new_servers)

    old_fields = '''  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
  private diagnostics = new Map<string, unknown[]>();
  private initialized: Promise<void>;'''
    new_fields = '''  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
  private diagnostics = new Map<string, unknown[]>();
  private opened = new Map<string, { version: number; text: string }>();
  private initialized: Promise<void>;'''
    if text.count(old_fields) != 1:
        raise RuntimeError("unexpected LSP client field block")
    text = text.replace(old_fields, new_fields)

    old_open = '''  async open(filePath: string): Promise<{ uri: string; text: string }> {
    await this.initialized;
    const resolved = resolveWorkspacePath(filePath);
    const text = fs.readFileSync(resolved.absolute, "utf8");
    const uri = pathToFileURL(resolved.absolute).href;
    this.notify("textDocument/didOpen", {
      textDocument: { uri, languageId: this.config.language_id, version: 1, text },
    });
    return { uri, text };
  }'''
    new_open = '''  async open(filePath: string): Promise<{ uri: string; text: string }> {
    await this.initialized;
    const resolved = resolveWorkspacePath(filePath);
    const text = fs.readFileSync(resolved.absolute, "utf8");
    const uri = pathToFileURL(resolved.absolute).href;
    const prior = this.opened.get(uri);
    if (!prior) {
      this.notify("textDocument/didOpen", {
        textDocument: { uri, languageId: this.config.language_id, version: 1, text },
      });
      this.opened.set(uri, { version: 1, text });
    } else if (prior.text !== text) {
      const version = prior.version + 1;
      this.notify("textDocument/didChange", {
        textDocument: { uri, version },
        contentChanges: [{ text }],
      });
      this.opened.set(uri, { version, text });
    }
    return { uri, text };
  }'''
    if text.count(old_open) != 1:
        raise RuntimeError("unexpected LSP open block")
    text = text.replace(old_open, new_open)

    old_ast_ok = '''    ok: result.code === 0,
    engine: "ast-grep",'''
    new_ast_ok = '''    ok: result.code === 0 || result.code === 1,
    engine: "ast-grep",'''
    if text.count(old_ast_ok) != 1:
        raise RuntimeError("unexpected ast-grep search status block")
    text = text.replace(old_ast_ok, new_ast_ok)

    old_split = 'const lines = text.split("\\n");'
    if text.count(old_split) != 2:
        raise RuntimeError(f"expected two anchored line splits, found {text.count(old_split)}")
    text = text.replace(old_split, 'const lines = text.split(/\\r?\\n/);')

    old_join = '''        const replacementLines = params.replacement.split("\\n");
        const next = [...lines.slice(0, start), ...replacementLines, ...lines.slice(end + 1)].join("\\n");'''
    new_join = '''        const newline = text.includes("\\r\\n") ? "\\r\\n" : "\\n";
        const replacementLines = params.replacement.replace(/\\r\\n/g, "\\n").split("\\n");
        const next = [...lines.slice(0, start), ...replacementLines, ...lines.slice(end + 1)].join(newline);'''
    if text.count(old_join) != 1:
        raise RuntimeError("unexpected anchored replacement block")
    text = text.replace(old_join, new_join)

    extension.write_text(text, encoding="utf-8")


def post() -> None:
    runtime = ROOT / "src/app/agent_runtime/pi_runtime_core.py"
    old = '''    tools = sorted({tool for capability, tool in mapping.items() if capability in spec.capabilities})
    if tools:
        argv.extend(["--tools", ",".join(tools)])
    else:
        argv.append("--no-builtin-tools")'''
    new = '''    extension_tools: set[str] = set()
    if "workspace.lsp" in spec.capabilities:
        extension_tools.update({
            "lsp_diagnostics", "lsp_hover", "lsp_definition", "lsp_references",
            "lsp_document_symbols", "lsp_workspace_symbols", "engineering_diagnostics",
        })
    if "workspace.ast_search" in spec.capabilities:
        extension_tools.update({"ast_grep", "engineering_diagnostics"})
    if "workspace.anchored_edit" in spec.capabilities:
        extension_tools.update({"anchored_read", "anchored_edit"})
    if "agent.clarify" in spec.capabilities:
        extension_tools.add("ask_user_question")
    if "agent.context" in spec.capabilities:
        extension_tools.update({"context_info", "compact_context"})
    if spec.external_capabilities:
        extension_tools.add("omnix_capability")
    tools = sorted(
        {tool for capability, tool in mapping.items() if capability in spec.capabilities}
        | extension_tools
    )
    if tools:
        argv.extend(["--tools", ",".join(tools)])
    else:
        argv.append("--no-builtin-tools")'''
    _replace(runtime, old, new)
    _harden_engineering_extension()

    tests = ROOT / "src/tests/agent_runtime/test_pi_engineering_tools.py"
    source = tests.read_text(encoding="utf-8")
    marker = "def test_pi_explicitly_allowlists_governed_extension_tools"
    if marker not in source:
        source += '''

def test_pi_explicitly_allowlists_governed_extension_tools(tmp_path: Path) -> None:
    spec = _spec(
        tmp_path,
        [
            "workspace.read", "workspace.lsp", "workspace.ast_search",
            "workspace.anchored_edit", "agent.clarify", "agent.context",
        ],
    ).model_copy(update={"external_capabilities": ["github.inspect_ci"]})
    argv = pi_rpc_argv(spec, pi_path="pi")
    tools = argv[argv.index("--tools") + 1].split(",")
    for expected in (
        "lsp_diagnostics", "lsp_references", "engineering_diagnostics", "ast_grep",
        "anchored_read", "anchored_edit", "ask_user_question", "context_info",
        "compact_context", "omnix_capability",
    ):
        assert expected in tools
'''
    source_marker = "def test_engineering_extension_runtime_hardening_contract"
    if source_marker not in source:
        source += '''

def test_engineering_extension_runtime_hardening_contract() -> None:
    source = Path("src/app/agent_runtime/pi_engineering_extension.ts").read_text(encoding="utf-8")
    assert 'OMNIX_AGENT_AST_GREP_COMMAND || "ast-grep"' in source
    assert 'result.code === 0 || result.code === 1' in source
    assert 'textDocument/didChange' in source
    assert 'text.includes("\\r\\n") ? "\\r\\n" : "\\n"' in source
'''
    tests.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    if mode == "prepare":
        prepare()
    elif mode == "post":
        post()
    else:
        raise SystemExit(f"unknown mode: {mode}")
