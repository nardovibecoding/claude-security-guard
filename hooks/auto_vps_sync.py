#!/usr/bin/env python3
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
    if ok:
        return f"VPS auto-synced after git push. HEAD: {out[-40:] if out else 'ok'}"
    return f"VPS sync FAILED: {out}"


if __name__ == "__main__":
    run_hook(check, action, "auto_vps_sync")
