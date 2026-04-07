#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PostToolUse hook: catch Telegram command handlers missing @admin_only decorator.

Catches:
- async def cmd_* or async def handle_* registered as CommandHandler
  without @admin_only, @require_auth, or an explicit ALLOWED_USERS check

This is a HARD BLOCK on bot_base.py and admin_bot.py edits. Soft warning elsewhere.

Commits this prevents: e21bbdc (12) — 6 commands missing @admin_only
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# Sensitive command prefixes that should always require auth
_SENSITIVE_PREFIXES = re.compile(
    r"^\s*async\s+def\s+(cmd_(start|stop|config|status|version|restart|kill|panel|"
    r"eval|exec|shell|debug|admin|deploy|reset|clear|wipe|export|import|"
    r"redteam|test|set|get|update|reload|sync|flush|purge|log|logs|"
    r"add|remove|ban|unban|grant|revoke|approve|deny|"
    r"models?|provider|routing|memory|session|token|key))\s*\(",
    re.IGNORECASE
)

# Auth patterns
_AUTH_DECORATOR = re.compile(r"@(admin_only|require_auth|admin_required|check_admin)")
_AUTH_INLINE = re.compile(
    r"(ALLOWED_USERS|admin_only|is_admin|user_id\s*(not\s+in|==)\s*ADMIN|"
    r"ADMIN_USER_ID|require_auth)"
)

# Files this hook actively monitors
_TARGET_FILES = {"bot_base.py", "admin_bot.py"}


def _scan(content, fname):
    lines = content.splitlines()
    warnings = []

    for i, line in enumerate(lines, 1):
        if not _SENSITIVE_PREFIXES.match(line):
            continue

        # Look at the 5 lines BEFORE this def for a decorator
        before = "\n".join(lines[max(0, i-6):i-1])
        # Look at the first 10 lines of the function body for inline auth
        after = "\n".join(lines[i:min(len(lines), i+10)])

        has_auth = (
            _AUTH_DECORATOR.search(before) or
            _AUTH_INLINE.search(after)
        )

        if not has_auth:
            func_name = re.search(r"async\s+def\s+(\w+)", line)
            fname_str = func_name.group(1) if func_name else "?"
            warnings.append(
                f"  line ~{i}: `{fname_str}` — "
                "sensitive command handler without @admin_only or auth check. "
                "Add @admin_only decorator or explicit ALLOWED_USERS check at the top."
            )

    return warnings


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    if "admin_only_guard" in fp:
        return False
    # Only run on bot files
    fname = Path(fp).name
    return fname in _TARGET_FILES or "bot" in fname.lower() or "admin" in fname.lower()


def action(tool_name, tool_input, _input_data):
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    fp = tool_input.get("file_path", "")
    fname = Path(fp).name
    warnings = _scan(content, fname)
    if not warnings:
        return None

    return (
        f"ADMIN ONLY GUARD: unprotected command handlers in `{fname}`.\n"
        "Every command that touches config/state/bots requires @admin_only.\n"
        + "\n".join(warnings[:6])
    )


if __name__ == "__main__":
    run_hook(check, action, "admin_only_guard")
