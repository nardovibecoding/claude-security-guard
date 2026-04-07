#!/usr/bin/env python3
"""PostToolUse hook: auto-restart process after editing its source file."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# Map: file pattern → restart command
# VPS bots: pkill via SSH, start_all.sh auto-restarts
# Mac scripts: pkill locally, launchd auto-restarts
RESTART_MAP = {
    # VPS bots — core files (restart everything)
    "admin_bot": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"'",
    "bot_base.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python run_bot\"'",  # restarts ALL persona bots
    "config.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",  # config affects everything
    "callbacks.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"'",
    # VPS bots — shared libraries (affect all bots)
    "llm_client.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",
    "utils.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",
    "memory.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",
    "sanitizer.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",
    "conversation_compressor.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",
    "conversation_logger.py": "ssh -o ConnectTimeout=5 {vps} 'pkill -f \"python admin_bot\"; pkill -f \"python run_bot\"'",
    # VPS — auto-reply service
    "auto_reply.py": "ssh -o ConnectTimeout=5 {vps} 'systemctl --user restart outreach-autoreply 2>/dev/null; pkill -f auto_reply 2>/dev/null'",
    # Mac scripts
    "voice_daemon.py": "pkill -f voice_daemon.py",
    "recording_indicator.py": "pkill -f recording_indicator.py",
    # No restart needed (runs fresh each time or handled elsewhere)
    "speak_hook.py": None,
    "run_bot.py": None,  # handled by auto_bot_restart.py for persona-specific
    "personas/": None,  # handled by auto_bot_restart.py
    # Digest/cron scripts — no restart needed, they run on schedule
    "news.py": None,
    "reddit_digest.py": None,
    "china_trends.py": None,
    "x_curator.py": None,
}


def _load_vps():
    env_path = Path.home() / "telegram-claude-bot" / ".env"
    user = "bernard"
    host = "157.180.28.14"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("VPS_USER="):
                user = line.split("=", 1)[1].strip()
            elif line.startswith("VPS_HOST="):
                host = line.split("=", 1)[1].strip()
    return f"{user}@{host}"


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return any(pattern in file_path for pattern in RESTART_MAP)


_DEBOUNCE_SECONDS = 10


def _debounce_ok(cmd: str) -> bool:
    """Return True if enough time has passed since the last restart with this command."""
    tag = hashlib.md5(cmd.encode()).hexdigest()[:8]
    ts_file = f"/tmp/.auto_restart_{tag}.ts"
    now = time.time()
    try:
        with open(ts_file) as f:
            last = float(f.read().strip())
        if now - last < _DEBOUNCE_SECONDS:
            return False
    except (FileNotFoundError, ValueError):
        pass
    with open(ts_file, "w") as f:
        f.write(str(now))
    return True


def action(tool_name, tool_input, input_data):
    file_path = tool_input.get("file_path", "")
    for pattern, cmd in RESTART_MAP.items():
        if pattern in file_path:
            if cmd is None:
                return None  # no restart needed
            vps = _load_vps()
            cmd = cmd.format(vps=vps)
            if not _debounce_ok(cmd):
                return f"Skipped restart for `{pattern}` (debounce: another restart was triggered <{_DEBOUNCE_SECONDS}s ago)."
            subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
            return f"Auto-restarted: `{pattern}` after edit. Process will auto-recover via launchd/start_all.sh."
    return None


if __name__ == "__main__":
    run_hook(check, action, "auto_restart_process")
