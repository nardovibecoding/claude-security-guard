#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""UserPromptSubmit hook: save memory + prompt /clear at 50% context."""
import json
import sys
from pathlib import Path

STATUSLINE_JSON = Path("/tmp/claude_statusline.json")
THRESHOLD_FILE = Path("/tmp/claude_ctx_last_threshold")
TRIGGER_PCT = 50


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    if not STATUSLINE_JSON.exists():
        print("{}")
        return

    try:
        data = json.loads(STATUSLINE_JSON.read_text())
        ctx_pct = float(data.get("context_window", {}).get("used_percentage", 0))
    except (ValueError, OSError, KeyError):
        print("{}")
        return

    if ctx_pct < TRIGGER_PCT:
        # Reset flag so next crossing fires again
        THRESHOLD_FILE.write_text("ready")
        print("{}")
        return

    # Only fire once per crossing (reset when ctx drops below threshold)
    fired = False
    if THRESHOLD_FILE.exists():
        try:
            fired = THRESHOLD_FILE.read_text().strip() == "fired"
        except OSError:
            pass

    if fired:
        print("{}")
        return

    THRESHOLD_FILE.write_text("fired")
    msg = (
        f"CONTEXT AT {ctx_pct:.0f}% — auto-save memory now, then tell the user "
        f"to type /clear to start a fresh session."
    )
    print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
