#!/usr/bin/env python3
"""Stop hook: remind to save content-worthy moments before session ends."""
import json
import os
import sys
from pathlib import Path

# Skip during convos (auto-clear flow)
_tty = os.environ.get("CLAUDE_TTY_ID", "").strip()
if Path(f"/tmp/claude_ctx_exit_pending_{_tty}").exists() if _tty else Path("/tmp/claude_ctx_exit_pending").exists():
    print("{}")
    sys.exit(0)

CONTENT_LOG = Path.home() / "telegram-claude-bot" / "content_drafts" / "running_log.md"
CTX_FILE = Path("/tmp/claude_ctx_pct")


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    # Check if context is high enough that session is substantial
    ctx_pct = 0
    if CTX_FILE.exists():
        try:
            ctx_pct = float(CTX_FILE.read_text().strip())
        except (ValueError, OSError):
            pass

    # Only trigger if session is substantial (>15% context used)
    if ctx_pct < 15:
        print("{}")
        return

    # Check if anything was already saved to content log this session
    already_saved = False
    if CONTENT_LOG.exists():
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            content = CONTENT_LOG.read_text()
            already_saved = today in content
        except Exception:
            pass

    if already_saved:
        print("{}")
        return

    # Prompt Claude to save content
    msg = (
        "📝 **Session ending — any content worth capturing?**\n"
        "If this session had insights, discoveries, or results worth tweeting:\n"
        "Call `content_capture` with the key moments before /clear.\n"
        "Categories: insight, result, code, number, journey, mistake"
    )
    print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
