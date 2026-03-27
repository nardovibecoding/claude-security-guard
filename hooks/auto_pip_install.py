#!/usr/bin/env python3
"""PostToolUse hook: auto pip install on VPS after requirements.txt edit."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook, ssh_cmd
from vps_config import VPS_REPO


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return file_path.endswith("requirements.txt")


def action(tool_name, tool_input, input_data):
    ok, out = ssh_cmd(
        f"cd {VPS_REPO} && source venv/bin/activate && pip install -r requirements.txt -q",
        timeout=30
    )
    if ok:
        return "VPS: pip install -r requirements.txt completed."
    return f"VPS pip install FAILED: {out[:200]}"


if __name__ == "__main__":
    run_hook(check, action, "auto_pip_install")
