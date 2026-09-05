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
        tests.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    if mode == "prepare":
        prepare()
    elif mode == "post":
        post()
    else:
        raise SystemExit(f"unknown mode: {mode}")
