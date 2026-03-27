#!/usr/bin/env python3
"""UserPromptSubmit hook: auto-trigger checkpoint at 20% context intervals."""
import json
import sys
from pathlib import Path

CTX_FILE = Path("/tmp/claude_ctx_pct")
THRESHOLD_FILE = Path("/tmp/claude_ctx_last_threshold")

# Thresholds where we trigger
THRESHOLDS = [20, 40, 60, 80]


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    # Read current context %
    if not CTX_FILE.exists():
        print("{}")
        return

    try:
        ctx_pct = float(CTX_FILE.read_text().strip())
    except (ValueError, OSError):
        print("{}")
        return

    # Read last triggered threshold
    last_threshold = 0
    if THRESHOLD_FILE.exists():
        try:
            last_threshold = int(THRESHOLD_FILE.read_text().strip())
        except (ValueError, OSError):
            pass

    # Check if we crossed a new threshold
    current_threshold = 0
    for t in THRESHOLDS:
        if ctx_pct >= t:
            current_threshold = t

    if current_threshold > last_threshold and current_threshold > 0:
        # Save new threshold
        THRESHOLD_FILE.write_text(str(current_threshold))

        if current_threshold >= 80:
            msg = (
                f"⚠️ **Context at {ctx_pct:.0f}%** — CRITICAL. "
                f"Call `session_checkpoint` NOW with a summary of this session, "
                f"then suggest /clear to the user."
            )
        elif current_threshold >= 60:
            msg = (
                f"⚠️ **Context at {ctx_pct:.0f}%** — HIGH. "
                f"Call `session_checkpoint` to save session state. "
                f"Recommend /clear to the user."
            )
        elif current_threshold >= 40:
            msg = (
                f"📋 **Context at {ctx_pct:.0f}%** — "
                f"Call `session_checkpoint` to save progress. "
                f"Offer /clear if the current task is complete."
            )
        else:  # 20%
            msg = (
                f"📋 **Context at {ctx_pct:.0f}%** — "
                f"Quick save: note any key decisions or findings that shouldn't be lost."
            )

        print(json.dumps({"systemMessage": msg}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
