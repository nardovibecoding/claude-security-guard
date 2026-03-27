#!/usr/bin/env python3
"""PreToolUse hook: block destructive ops (rm -rf, force push, hard reset) + VPS direct access (scp, manual bot start, kill start_all)."""
import re
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook


def check(tool_name, tool_input, input_data):
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(re.search(
        # Destructive ops (#1, #2)
        r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force)|rm\s+-rf|"
        r"git\s+push\s+(-[a-zA-Z]*f|--force)|git\s+reset\s+--hard|"
        r"git\s+checkout\s+\.|git\s+clean\s+-[a-zA-Z]*f|"
        # VPS direct access — scp/rsync (#3, #4)
        r"(scp|rsync)\s+.*157\.180|"
        # VPS direct access — ssh write (#5)
        r"ssh\s+.*cat\s*>|ssh\s+.*sed\s+-i|ssh\s+.*tee\s|"
        # Manual bot start (#6)
        r"ssh\s+.*python.*bot|python\s+(admin_bot|run_bot)|"
        # Kill start_all (#7)
        r"kill.*start_all|pkill.*start_all|"
        # sed in-place (#8)
        r"sed\s+(-[a-zA-Z]*i|--in-place)|"
        # pip/npm/curl install (#9)
        r"pip3?\s+install|npm\s+install|curl\s+.*\|\s*(ba)?sh|"
        # Log overwrite (#10)
        r">\s*/tmp/.*\.log\s|"
        # Bad subprocess $$ (#11)
        r"grep\s+-v\s+\$\$|pgrep.*grep.*\$\$|"
        # Agent git push (#13)
        r"Agent.*git\s+push|agent.*push.*origin",
        cmd
    ))


def action(tool_name, tool_input, input_data):
    return None  # Block via deny, message in hookSpecificOutput


def check_and_deny(tool_name, tool_input, input_data):
    """Return deny decision for PreToolUse."""
    if not check(tool_name, tool_input, input_data):
        return None
    cmd = tool_input.get("command", "")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny"
        },
        "systemMessage": f"**BLOCKED: Destructive operation.** `{cmd[:80]}` — ask Bernard for confirmation."
    }


if __name__ == "__main__":
    import json
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        sys.exit()
    result = check_and_deny(
        input_data.get("tool_name", ""),
        input_data.get("tool_input", {}),
        input_data
    )
    print(json.dumps(result or {}))
