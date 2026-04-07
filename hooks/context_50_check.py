#!/usr/bin/env python3
"""UserPromptSubmit hook: force /s when context hits 50%.

Fires at the start of every user turn. Checks statusline JSON for context %.
At >=50%, injects urgent systemMessage telling Claude to run /s first.

Fires on EVERY turn above 50%. Resets naturally after /s triggers /clear.
Uses exit 0 + systemMessage (not exit 2, which blocks user prompt entirely).
"""
import json
import sys
from pathlib import Path

STATUSLINE_JSON = Path("/tmp/claude_statusline.json")
TRIGGER_PCT = 35


def main():
    try:
        hook_input = json.load(sys.stdin)
        prompt = hook_input.get("prompt", "")
        hook_session = hook_input.get("session_id", "")
    except (json.JSONDecodeError, EOFError):
        prompt = ""
        hook_session = ""

    # Don't block if user is already running /s
    if prompt.strip().startswith("/s"):
        print("{}")
        return

    if not STATUSLINE_JSON.exists():
        print("{}")
        return

    try:
        data = json.loads(STATUSLINE_JSON.read_text())
        ctx_pct = float(data.get("context_window", {}).get("used_percentage", 0))
        file_session = data.get("session_id", "")
    except (ValueError, OSError, KeyError):
        print("{}")
        return

    # Stale statusline from a different session — ignore
    if hook_session and file_session and hook_session != file_session:
        print("{}")
        return

    done_marker = Path("/tmp/claude_auto_save_done")

    if ctx_pct < TRIGGER_PCT:
        # Context dropped (after /clear) — reset the done marker
        done_marker.unlink(missing_ok=True)
        print("{}")
        return

    # Skip if already saved this cycle
    if done_marker.exists():
        print("{}")
        return

    # Write marker file for PreToolUse hook to pick up
    marker = Path("/tmp/claude_auto_save_needed")
    marker.write_text(json.dumps({"pct": ctx_pct, "ts": str(Path("/tmp/claude_statusline.json").stat().st_mtime)}))

    # Inject into Claude's context via additionalContext
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"CONTEXT AT {ctx_pct:.0f}%. Auto-save now. "
                f"1. Set tab title (bash, foreground). "
                f"2. Spawn ONE background Agent (model=sonnet, run_in_background=true) to: "
                f"write convo summary to memory, add MEMORY.md pointer, file atoms to ~/NardoWorld/. "
                f"3. Print 'Saving... /clear' so user can /clear immediately. "
                f"4. Then answer the user's message normally. "
                f"Do not ask permission. Do this alongside your response."
            )
        }
    }))


if __name__ == "__main__":
    main()
