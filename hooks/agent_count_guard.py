#!/usr/bin/env python3
"""PreToolUse hook: block >1 agent per turn, force Claude to ask user.
After user approves (sets allowed count), allow up to that many within the turn."""
import json
import sys
import time
from pathlib import Path

COUNTER_FILE = Path("/tmp/claude_agent_spawn_counter.json")
TURN_TIMEOUT = 120  # reset counter after 120s gap (new turn)
MAX_ALLOWED = 3  # absolute ceiling


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Agent":
        print("{}")
        return

    # Auto-save agents (background, save-related) bypass the cap
    tool_input = input_data.get("tool_input", {})
    is_autosave = (
        tool_input.get("run_in_background") is True
        and any(kw in tool_input.get("prompt", "").lower() for kw in ["convo summary", "memory", "save", "nardoworld"])
    )
    if is_autosave:
        print("{}")
        return

    now = time.time()

    # Load or reset counter
    state = {"count": 0, "allowed": 1, "ts": now}
    if COUNTER_FILE.exists():
        try:
            state = json.loads(COUNTER_FILE.read_text())
            if now - state.get("ts", 0) > TURN_TIMEOUT:
                state = {"count": 0, "allowed": 1, "ts": now}
        except (json.JSONDecodeError, OSError):
            state = {"count": 0, "allowed": 1, "ts": now}

    state["count"] += 1
    state["ts"] = now
    allowed = state.get("allowed", 1)
    COUNTER_FILE.write_text(json.dumps(state))

    if state["count"] > allowed:
        # Block and tell Claude to ask how many
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"BLOCKED: Agent #{state['count']} (allowed: {allowed}). Ask Bernard how many agents he wants first.",
                "additionalContext": f"You tried to spawn more than {allowed} agent(s). STOP. Ask Bernard how many agents, then write the approved count to {COUNTER_FILE} as JSON with key 'allowed' (max {MAX_ALLOWED}).",
            }
        }
        print(json.dumps(result))
        return

    # Within allowed limit
    print("{}")


if __name__ == "__main__":
    main()
