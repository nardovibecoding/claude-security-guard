# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""Base class for PostToolUse hooks. Reads JSON from stdin, routes to handler."""
import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

DEBUG_LOG = Path("/tmp/claude_hooks_debug.log")
DEBUG = os.environ.get("CLAUDE_HOOKS_DEBUG", "0") == "1"


def _log(hook_name, msg):
    """Append to debug log if DEBUG enabled."""
    if not DEBUG:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"[{ts}] {hook_name}: {msg}\n")


def run_hook(check_fn, action_fn, hook_name="unknown"):
    """Standard hook runner pattern.

    check_fn(tool_name, tool_input, input_data) -> bool
    action_fn(tool_name, tool_input, input_data) -> str (message) or None
    """
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _log(hook_name, "bad stdin")
        print("{}")
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    _log(hook_name, f"tool={tool_name} input_keys={list(tool_input.keys())}")

    if not check_fn(tool_name, tool_input, input_data):
        _log(hook_name, "no match")
        print("{}")
        return

    _log(hook_name, "MATCHED — running action")
    message = action_fn(tool_name, tool_input, input_data)
    if message:
        _log(hook_name, f"result: {message[:100]}")
        print(json.dumps({"systemMessage": message}))
    else:
        _log(hook_name, "action returned None")
        print("{}")


def ssh_cmd(cmd, timeout=10):
    """Run command on VPS via SSH. Returns (success, output)."""
    sys.path.insert(0, str(Path(__file__).parent))
    from vps_config import VPS_SSH

    _log("ssh", f"running: ssh {VPS_SSH} {cmd[:80]}")
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", VPS_SSH, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        ok = result.returncode == 0
        _log("ssh", f"{'ok' if ok else 'FAIL'}: {result.stdout[:80] or result.stderr[:80]}")
        return ok, result.stdout.strip()
    except subprocess.TimeoutExpired:
        _log("ssh", "TIMEOUT")
        return False, "SSH timeout"
    except Exception as e:
        _log("ssh", f"ERROR: {e}")
        return False, str(e)
