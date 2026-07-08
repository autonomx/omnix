from pathlib import Path

patches = {
    "src/app/chat/memory_prompt.py": (
        "import os\n",
        "",
        "from app.assistant_memory import MemoryService, default_memory_service, resolve_chat_scope\n",
        "from app.assistant_memory import MemoryService, default_memory_service, resolve_chat_scope\nfrom app.assistant_memory.settings import load_memory_runtime_settings\n",
        """def chat_memory_enabled() -> bool:
    return (os.environ.get(\"OMNIX_CHAT_MEMORY_ENABLED\") or \"\").strip().lower() in {
        \"1\",
        \"true\",
        \"yes\",
        \"on\",
    }
""",
        """def chat_memory_enabled() -> bool:
    return load_memory_runtime_settings().curated_memory_enabled
""",
    ),
    "src/app/assistant_memory/jobs.py": (
        "import os\n",
        "",
        "from .scope import resolve_chat_scope\n",
        "from .scope import resolve_chat_scope\nfrom .settings import load_memory_runtime_settings\n",
        """def memory_suggestions_enabled() -> bool:
    return (os.environ.get(\"OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED\") or \"\").strip().lower() in {
        \"1\", \"true\", \"yes\", \"on\",
    }
""",
        """def memory_suggestions_enabled() -> bool:
    return load_memory_runtime_settings().suggestions_enabled
""",
    ),
    "src/app/chat/history_search.py": (
        "import os\n",
        "",
        "from .prompt_assembly import PromptHistoryItem\n",
        "from app.assistant_memory.settings import load_memory_runtime_settings\n\nfrom .prompt_assembly import PromptHistoryItem\n",
        """def history_recall_enabled() -> bool:
    return (os.environ.get(\"OMNIX_CHAT_HISTORY_RECALL_ENABLED\") or \"\").strip().lower() in {
        \"1\",
        \"true\",
        \"yes\",
        \"on\",
    }
""",
        """def history_recall_enabled() -> bool:
    return load_memory_runtime_settings().history_recall_enabled
""",
    ),
    "src/app/chat/compaction.py": (
        "import os\n",
        "import os\n",
        "from app.jobs import CompleteJobRequest, CreateJobRequest, JobRecord, ResourceClass, SQLiteJobStore, default_job_store\n",
        "from app.assistant_memory.settings import load_memory_runtime_settings\nfrom app.jobs import CompleteJobRequest, CreateJobRequest, JobRecord, ResourceClass, SQLiteJobStore, default_job_store\n",
        """def compaction_enabled() -> bool:
    return (os.environ.get(\"OMNIX_CHAT_COMPACTION_ENABLED\") or \"\").strip().lower() in {
        \"1\", \"true\", \"yes\", \"on\",
    }
""",
        """def compaction_enabled() -> bool:
    return load_memory_runtime_settings().compaction_enabled
""",
    ),
    "src/app/assistant_memory/hermes_adapter.py": (
        "import os\n",
        "import os\n",
        "from .models import MemoryRecord, MemoryScopeContext\n",
        "from .models import MemoryRecord, MemoryScopeContext\nfrom .settings import load_memory_runtime_settings\n",
        """def hermes_memory_sync_enabled() -> bool:
    return (os.environ.get(\"OMNIX_HERMES_MEMORY_SYNC_ENABLED\") or \"\").strip().lower() in {
        \"1\",
        \"true\",
        \"yes\",
        \"on\",
    }
""",
        """def hermes_memory_sync_enabled() -> bool:
    return load_memory_runtime_settings().hermes_sync_enabled
""",
    ),
}

for filename, (remove_import, replace_import, marker, marker_replacement, old_func, new_func) in patches.items():
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    if remove_import != replace_import:
        if text.count(remove_import) != 1:
            raise SystemExit(f"import removal missing in {filename}")
        text = text.replace(remove_import, replace_import, 1)
    if text.count(marker) != 1:
        raise SystemExit(f"import marker missing in {filename}")
    text = text.replace(marker, marker_replacement, 1)
    if text.count(old_func) != 1:
        raise SystemExit(f"flag function missing in {filename}")
    path.write_text(text.replace(old_func, new_func, 1), encoding="utf-8")

budget = Path("src/app/chat/context_budget.py")
text = budget.read_text(encoding="utf-8")
marker = "from pydantic import BaseModel, ConfigDict, Field\n"
replacement = marker + "\nfrom app.assistant_memory.settings import load_memory_runtime_settings\n"
if text.count(marker) != 1:
    raise SystemExit("context budget import marker missing")
text = text.replace(marker, replacement, 1)
old = """    return PromptBudget(
        max_input_tokens=max(1, integer(\"OMNIX_CHAT_INPUT_TOKEN_BUDGET\", DEFAULT_INPUT_TOKEN_BUDGET)),
        reserved_output_tokens=integer(\"OMNIX_CHAT_OUTPUT_TOKEN_RESERVE\", DEFAULT_OUTPUT_TOKEN_RESERVE),
        memory_tokens=integer(\"OMNIX_CHAT_MEMORY_TOKEN_BUDGET\", 4_000),
        summary_tokens=integer(\"OMNIX_CHAT_SUMMARY_TOKEN_BUDGET\", 4_000),
        history_tokens=integer(\"OMNIX_CHAT_HISTORY_TOKEN_BUDGET\", 8_000),
        external_context_tokens=integer(\"OMNIX_CHAT_EXTERNAL_CONTEXT_TOKEN_BUDGET\", 12_000),
    )
"""
new = """    memory_settings = load_memory_runtime_settings()
    return PromptBudget(
        max_input_tokens=max(1, integer(\"OMNIX_CHAT_INPUT_TOKEN_BUDGET\", DEFAULT_INPUT_TOKEN_BUDGET)),
        reserved_output_tokens=integer(\"OMNIX_CHAT_OUTPUT_TOKEN_RESERVE\", DEFAULT_OUTPUT_TOKEN_RESERVE),
        memory_tokens=memory_settings.memory_token_budget,
        summary_tokens=integer(\"OMNIX_CHAT_SUMMARY_TOKEN_BUDGET\", 4_000),
        history_tokens=memory_settings.history_token_budget,
        external_context_tokens=integer(\"OMNIX_CHAT_EXTERNAL_CONTEXT_TOKEN_BUDGET\", 12_000),
    )
"""
if text.count(old) != 1:
    raise SystemExit("prompt budget return block missing")
budget.write_text(text.replace(old, new, 1), encoding="utf-8")

routes = Path("src/app/assistant_memory/routes.py")
text = routes.read_text(encoding="utf-8")
text = text.replace(
    "from .management_routes import register_memory_management_routes\n",
    "from .management_routes import register_memory_management_routes\nfrom .settings_routes import register_memory_settings_routes\n",
    1,
)
old = """    register_memory_management_routes(
        app,
        chat_store_factory=chat_store_factory,
        memory_service_factory=memory_service_factory,
    )
"""
new = old + "    register_memory_settings_routes(app)\n"
if text.count(old) != 1:
    raise SystemExit("route registration block missing")
routes.write_text(text.replace(old, new, 1), encoding="utf-8")
