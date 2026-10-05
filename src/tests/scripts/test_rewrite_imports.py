"""scripts/rewrite_imports.py rewrites moved module paths exactly once (PA-5)."""
from __future__ import annotations

from scripts.rewrite_imports import rewrite_python, rewrite_text

MAPPING = [("app.old_pkg", "app.new.pkg")]


def test_imports_and_module_path_strings_are_rewritten() -> None:
    source = (
        "import app.old_pkg.runtime as runtime\n"
        "from app.old_pkg import contracts\n"
        "from app.old_pkg.store import (\n    Store,\n)\n"
        "from . import local\n"
        "TARGET = 'app.old_pkg.runtime.load'\n"
        "ENTRY = \"app.old_pkg.feature:FEATURE\"\n"
        "OTHER = 'app.old_pkg_extra.thing'\n"
        "TEXT = 'see app.old_pkg for details'\n"
    )

    rewritten = rewrite_python(source, MAPPING)

    assert rewritten == (
        "import app.new.pkg.runtime as runtime\n"
        "from app.new.pkg import contracts\n"
        "from app.new.pkg.store import (\n    Store,\n)\n"
        "from . import local\n"
        "TARGET = 'app.new.pkg.runtime.load'\n"
        "ENTRY = \"app.new.pkg.feature:FEATURE\"\n"
        "OTHER = 'app.old_pkg_extra.thing'\n"
        "TEXT = 'see app.old_pkg for details'\n"
    )
    assert rewrite_python(rewritten, MAPPING) == rewritten


def test_crlf_and_non_ascii_sources_keep_their_bytes_aligned() -> None:
    source = "# café\r\nfrom app.old_pkg import a\r\nX = 'app.old_pkg.b'\r\n"

    assert rewrite_python(source, MAPPING) == "# café\r\nfrom app.new.pkg import a\r\nX = 'app.new.pkg.b'\r\n"


def test_text_files_get_the_dotted_and_file_paths() -> None:
    text = "python -m app.old_pkg.cutover status\npaths: src/app/old_pkg/ and src/app/old_pkg_extra/\n"

    assert rewrite_text(text, MAPPING) == (
        "python -m app.new.pkg.cutover status\npaths: src/app/new/pkg/ and src/app/old_pkg_extra/\n"
    )


def test_docstrings_get_their_command_lines_rewritten() -> None:
    source = '"""Usage:\n\n    python -m app.old_pkg.cutover status\n"""\nX = 1\n'

    assert rewrite_python(source, MAPPING) == '"""Usage:\n\n    python -m app.new.pkg.cutover status\n"""\nX = 1\n'


def test_file_paths_with_their_suffix_are_rewritten() -> None:
    assert rewrite_text("- \"src/app/old_pkg.py\"\n", MAPPING) == "- \"src/app/new/pkg.py\"\n"
