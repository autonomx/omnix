from pathlib import Path
path = Path("src/app/assistant_memory/routes.py")
text = path.read_text(encoding="utf-8")
old = """    register_memory_management_routes(
        app,
        chat_store_factory=chat_store_factory,
        memory_service_factory=memory_service_factory,
    )
    register_memory_settings_routes(app)
"""
new = """    register_memory_settings_routes(app)
    register_memory_management_routes(
        app,
        chat_store_factory=chat_store_factory,
        memory_service_factory=memory_service_factory,
    )
"""
if text.count(old) != 1:
    raise SystemExit("memory route registration order block missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
