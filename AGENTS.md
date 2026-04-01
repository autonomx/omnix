# Agent Commands

## Linting and Type Checking

Since this is a Python project, here are recommended commands for linting and type checking:

- **Linting (code style and errors)**: `ruff check .`
- **Import sorting**: `ruff check --select I . --fix`
- **Type checking**: `mypy .`

To install these tools, run:
```
pip install ruff mypy
```

These commands should be run after code changes to ensure code quality.