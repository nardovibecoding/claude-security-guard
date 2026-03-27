#!/usr/bin/env python3
"""PostToolUse hook: auto-restart bot on VPS after persona JSON edit."""
import re
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook, ssh_cmd


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return bool(re.search(r"personas/\w+\.json$", file_path))


def action(tool_name, tool_input, input_data):
    file_path = tool_input.get("file_path", "")
    # Extract persona ID from path: personas/daliu.json -> daliu
    match = re.search(r"personas/(\w+)\.json$", file_path)
    if not match:
        return None
    persona_id = match.group(1)
    ok, out = ssh_cmd(f"pkill -f 'run_bot.py {persona_id}'")
    # pkill returns 1 if no process found — that's ok
    return f"VPS: killed run_bot.py {persona_id} — start_all.sh will auto-restart in ~10s."


if __name__ == "__main__":
    run_hook(check, action, "auto_bot_restart")
