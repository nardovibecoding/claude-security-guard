"""Shared VPS config — reads from .env single source of truth."""
import os
from pathlib import Path


def _load_env():
    """Load .env file without external dependencies."""
    env_path = Path(os.environ.get("PROJECT_ROOT", str(Path.home() / "your-project"))) / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env()

VPS_HOST = os.environ.get("VPS_HOST", os.environ.get("VPS_HOST", "<your-vps-ip>"))
VPS_USER = os.environ.get("VPS_USER", "bernard")
VPS_CLIPBOARD_PORT = os.environ.get("VPS_CLIPBOARD_PORT", "8888")
VPS_SSH = f"{VPS_USER}@{VPS_HOST}"
VPS_REPO = "${PROJECT_ROOT:-~/your-project}"
