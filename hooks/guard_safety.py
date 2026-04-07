#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PreToolUse hook: block destructive ops, VPS direct access, hook tampering, credential reads, git hook bypass, branch creation."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# --- Resolved credential directories (P0 #2) ---
_HOME = str(Path.home())
_CREDENTIAL_DIRS = [
    f"{_HOME}/.ssh/",
    f"{_HOME}/.aws/",
    f"{_HOME}/.gnupg/",
    f"{_HOME}/.kube/",
    f"{_HOME}/.config/gcloud/",
]

# --- Bash deny pattern (compiled once) ---
_BASH_DENY = re.compile(
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
    r"Agent.*git\s+push|agent.*push.*origin|"
    # Branch creation (#14) — force all commits to main
    r"git\s+(checkout\s+-b|switch\s+-c|branch\s+(?!-[dD]))|"
    # P1 #5 — block --no-verify / --no-gpg-sign on git commands
    r"git\s+(commit|push)\s+.*--no-verify|--no-verify\s+.*git\s+(commit|push)|"
    r"git\s+(commit|push)\s+.*--no-gpg-sign|--no-gpg-sign\s+.*git\s+(commit|push)"
)

# --- Splitter for compound commands (P0 #3) ---
_CMD_SPLIT = re.compile(r'\s*(?:&&|\|\||;|\||\$\(|`)\s*')


def _check_hook_path(path_str):
    """P0 #1: Return True if path targets security hooks directory."""
    if not path_str:
        return False
    expanded = path_str.replace("~", _HOME)
    return "/.claude/hooks/" in expanded or ".claude/hooks/" in expanded


def _check_credential_read(path_str):
    """P0 #2: Return True if path targets a credential directory."""
    if not path_str:
        return False
    expanded = path_str.replace("~", _HOME)
    try:
        resolved = str(Path(expanded).resolve())
    except Exception:
        resolved = expanded
    for cred_dir in _CREDENTIAL_DIRS:
        if resolved.startswith(cred_dir) or expanded.startswith(cred_dir):
            return True
    return False


def _check_bash_cmd(cmd):
    """P0 #3: Decompose compound bash commands and check each sub-command."""
    sub_commands = _CMD_SPLIT.split(cmd)
    for sub in sub_commands:
        sub = sub.strip()
        if sub and _BASH_DENY.search(sub):
            return True
    return False


def check(tool_name, tool_input, input_data):
    # P0 #1 — Block Write/Edit on hook files
    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path", "") or tool_input.get("path", "")
        if _check_hook_path(path):
            return "hook_protect"

    # P0 #2 — Block Read on credential directories
    if tool_name == "Read":
        path = tool_input.get("file_path", "") or tool_input.get("path", "")
        if _check_credential_read(path):
            return "credential_read"

    # Bash checks (P0 #3 compound decomposition + P1 #5 --no-verify + #14 branch)
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if _check_bash_cmd(cmd):
            return "bash_deny"

    return False


def action(tool_name, tool_input, input_data):
    return None


_REASONS = {
    "hook_protect": "Blocked: cannot modify security hooks. This protects against prompt injection disabling the security layer.",
    "credential_read": "Blocked: reading credential directories is restricted.",
    "bash_deny": None,
}


def check_and_deny(tool_name, tool_input, input_data):
    """Return deny decision for PreToolUse."""
    result = check(tool_name, tool_input, input_data)
    if not result:
        return None

    reason = _REASONS.get(result)

    if result == "bash_deny":
        cmd = tool_input.get("command", "")
        if re.search(r"--no-verify|--no-gpg-sign", cmd):
            reason = "Blocked: skipping git hooks/signing is not allowed."
        else:
            reason = f"**BLOCKED: Destructive operation.** `{cmd[:80]}` — requires user confirmation."

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny"
        },
        "systemMessage": reason
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
