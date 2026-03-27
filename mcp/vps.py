"""VPS SSH utilities with connection reuse."""

import os
import subprocess
from pathlib import Path


def load_env() -> dict:
    """Load .env from telegram-claude-bot (single source of truth)."""
    env = {
        "VPS_HOST": "157.180.28.14",
        "VPS_USER": "bernard",
        "VPS_CLIPBOARD_PORT": "8888",
    }
    env_path = Path.home() / "telegram-claude-bot" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in env:
                env[key] = value
    return env


def ssh_cmd(vps_ssh: str, cmd: str, timeout: int = 10) -> tuple[bool, str]:
    """Run command on VPS via SSH.

    Args:
        vps_ssh: user@host string
        cmd: command to run
        timeout: seconds before timeout

    Returns:
        (success, output) tuple
    """
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", vps_ssh, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "SSH timeout"
    except Exception as e:
        return False, str(e)
