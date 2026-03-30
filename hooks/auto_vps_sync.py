#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PostToolUse hook: auto-sync VPS after git push."""
import re
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook, ssh_cmd
from vps_config import VPS_REPO


def check(tool_name, tool_input, input_data):
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(re.search(r"git\s+push", cmd))


def action(tool_name, tool_input, input_data):
    ok, out = ssh_cmd(f"cd {VPS_REPO} && git fetch origin && git reset --hard origin/main")
    msg = f"VPS auto-synced after git push." if ok else f"VPS sync FAILED: {out}"

    # Auto-sync public repos if publishable files were pushed
    import subprocess
    from pathlib import Path
    sync_script = Path.home() / "telegram-claude-bot" / "scripts" / "sync_public_repos.py"
    if sync_script.exists():
        r = subprocess.run(
            ["python3", str(sync_script), "--sync"],
            capture_output=True, text=True, timeout=30)
        synced = r.stdout.count("COPIED")
        if synced:
            msg += f" Public repos: {synced} files synced."

    return msg


if __name__ == "__main__":
    run_hook(check, action, "auto_vps_sync")
