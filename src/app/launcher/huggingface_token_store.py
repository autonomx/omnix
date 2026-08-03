from __future__ import annotations

import os
import stat
from pathlib import Path

_TOKEN_FILE_NAME = "hugging_face_token.txt"
_PLACEHOLDER_VALUES = {
    "your_token",
    "your-token",
    "your hugging face token",
    "your_hugging_face_token",
    "hf_your_token",
}


def launcher_secret_directory(root: Path | None = None) -> Path:
    configured = os.environ.get("OMNIX_LAUNCHER_SECRET_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    resolved_root = root or Path(__file__).resolve().parents[3]
    return resolved_root / "resources" / "data" / "launcher" / "secrets"


def huggingface_token_path(root: Path | None = None) -> Path:
    return launcher_secret_directory(root) / _TOKEN_FILE_NAME


def validate_huggingface_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("Enter a Hugging Face access token.")
    if token.casefold() in _PLACEHOLDER_VALUES or "your_token" in token.casefold():
        raise ValueError("Replace the placeholder with a real Hugging Face access token.")
    if any(character.isspace() for character in token):
        raise ValueError("The Hugging Face token must not contain spaces or line breaks.")
    if not token.startswith("hf_"):
        raise ValueError("Hugging Face access tokens should begin with 'hf_'.")
    if len(token) < 20:
        raise ValueError("The Hugging Face token appears to be incomplete.")
    return token


def save_huggingface_token(value: str, root: Path | None = None) -> Path:
    token = validate_huggingface_token(value)
    path = huggingface_token_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass

    temporary = path.with_suffix(".tmp")
    temporary.write_text(token + "\n", encoding="utf-8")
    try:
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    temporary.replace(path)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    os.environ["HUGGING_FACE_HUB_TOKEN"] = token
    return path


def clear_huggingface_token(root: Path | None = None) -> bool:
    path = huggingface_token_path(root)
    removed = False
    try:
        path.unlink()
        removed = True
    except FileNotFoundError:
        pass
    os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
    return removed


def load_huggingface_token(root: Path | None = None) -> str | None:
    path = huggingface_token_path(root)
    if path.is_file():
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if token:
            try:
                return validate_huggingface_token(token)
            except ValueError:
                return None

    environment_token = os.environ.get("HUGGING_FACE_HUB_TOKEN", "").strip()
    if environment_token:
        try:
            return validate_huggingface_token(environment_token)
        except ValueError:
            return None
    return None


def huggingface_token_status(root: Path | None = None) -> dict[str, object]:
    path = huggingface_token_path(root)
    local_token = None
    if path.is_file():
        try:
            local_token = validate_huggingface_token(
                path.read_text(encoding="utf-8").strip()
            )
        except (OSError, ValueError):
            local_token = None

    environment_token = os.environ.get("HUGGING_FACE_HUB_TOKEN", "").strip()
    environment_valid = False
    if environment_token:
        try:
            validate_huggingface_token(environment_token)
            environment_valid = True
        except ValueError:
            environment_valid = False

    configured = bool(local_token or environment_valid)
    source = "local_file" if local_token else "environment" if environment_valid else None
    return {
        "configured": configured,
        "source": source,
        "local_path": str(path) if local_token else None,
    }
