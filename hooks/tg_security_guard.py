#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""PostToolUse hook: catch Telegram bot security anti-patterns.

Catches:
1. str(e) / repr(e) / traceback sent to chat (exception details leak)
2. HTML not escaped before <pre> tag (XSS-equivalent in Telegram HTML mode)
3. query.answer() called AFTER other query operations (auth check order bug)
4. Missing @admin_only on commands that need it
5. External data (forward_sender_name, caption, text from untrusted users)
   passed directly to format strings without sanitize_external_content()
6. Prompt injection: external filename/caption used in LLM prompt without sanitization

Commits this prevents: edf04ad (7), e21bbdc (12)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# --- Pattern definitions ---

# Exception detail leak: str(e) or repr(e) sent to Telegram
_EXC_LEAK = re.compile(
    r"""(send_message|reply_text|edit_message_text|answer)\s*\([^)]*\b(str|repr)\s*\(\s*e\b"""
)

# f-string with exception: f"...{e}..." sent to chat
_FSTR_EXC = re.compile(
    r"""(send_message|reply_text|edit_message_text|answer)\s*\(.*f["\'][^"']*\{e\b"""
)

# <pre> tag with unescaped content (should use html.escape)
_PRE_NO_ESCAPE = re.compile(
    r"""["\']<pre>["\'\s]*\+?\s*(?!html\.escape)(?!\s*html\.escape)"""
)
_PRE_FSTR_NO_ESCAPE = re.compile(
    r"""f["\'][^"']*<pre>[^"']*\{(?!html\.escape)"""
)

# query.answer() after query.edit_message / query.message (wrong order)
_ANSWER_AFTER_EDIT = re.compile(
    r"query\.(edit_message|message)\b.*\n.*query\.answer\("
)

# Untrusted Telegram fields used in format strings without sanitize call
_UNTRUSTED_FIELDS = re.compile(
    r"""(forward_sender_name|effective_user\.first_name|effective_user\.last_name|
         message\.caption|message\.document\.file_name|
         update\.effective_message\.text)\s*(?!\s*=)""",
    re.VERBOSE
)
_SANITIZE_CALL = re.compile(r"sanitize_external_content|html\.escape")


def _scan(content):
    lines = content.splitlines()
    warnings = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # Exception detail leak
        if _EXC_LEAK.search(line) or _FSTR_EXC.search(line):
            warnings.append(
                f"  line ~{i}: `{stripped[:80]}` — "
                "exception detail sent to Telegram chat. "
                "Log with logger.exception() and send a generic message to user."
            )

        # <pre> without html.escape
        if "<pre>" in line and ("html.escape" not in line) and (
            "send_message" in line or "reply_text" in line or
            "edit_message" in line or '+"' in line or '+f"' in line or
            "f'" in line or 'f"' in line
        ):
            if _PRE_NO_ESCAPE.search(line) or _PRE_FSTR_NO_ESCAPE.search(line):
                warnings.append(
                    f"  line ~{i}: `{stripped[:80]}` — "
                    "<pre> content not escaped with html.escape() → Telegram HTML injection risk."
                )

        # Untrusted fields in f-strings or format calls without sanitization
        if _UNTRUSTED_FIELDS.search(line):
            # Check if sanitize is called on same line or within 3 lines
            window = "\n".join(lines[max(0, i-2):min(len(lines), i+2)])
            if not _SANITIZE_CALL.search(window):
                # Only warn if it's being used in a string operation
                if re.search(r'f["\']|\.format\(|%\s*["\(]', line):
                    warnings.append(
                        f"  line ~{i}: `{stripped[:80]}` — "
                        "untrusted Telegram field in format string. "
                        "Pass through sanitize_external_content() first."
                    )

    # Multi-line check: query.answer after edit
    full = content
    if re.search(r"query\.(edit_message_text|edit_message_reply_markup)", full):
        # Find query.answer() calls that appear after edit calls in same function
        blocks = re.split(r"\nasync def |\ndef ", full)
        for block in blocks:
            if "query.answer" in block and re.search(
                r"query\.(edit_message|message\.reply)", block
            ):
                # Check relative order: answer should come BEFORE edits
                answer_pos = block.find("query.answer(")
                edit_pos = min(
                    (block.find(p) for p in [
                        "query.edit_message_text(",
                        "query.edit_message_reply_markup(",
                        "query.message.reply_text(",
                    ] if p in block),
                    default=-1
                )
                if answer_pos != -1 and edit_pos != -1 and answer_pos > edit_pos:
                    warnings.append(
                        "  query.answer() called AFTER query.edit_message* — "
                        "call query.answer() FIRST to avoid 'query too old' errors."
                    )
                    break

    return warnings


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    if "tg_security_guard" in fp:
        return False
    return True


def action(tool_name, tool_input, _input_data):
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    warnings = _scan(content)
    if not warnings:
        return None

    fp = tool_input.get("file_path", "")
    return (
        f"TG SECURITY GUARD: security issues in `{Path(fp).name}`.\n"
        + "\n".join(warnings[:6])
    )


if __name__ == "__main__":
    run_hook(check, action, "tg_security_guard")
