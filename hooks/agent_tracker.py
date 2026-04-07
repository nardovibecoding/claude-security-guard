#!/usr/bin/env python3
"""Track background agents across /clear boundaries.

Runs in TWO modes:
- PreToolUse (Agent): log agent spawn with description + prompt snippet
- SubagentStop: update agent entry with completion status

Tracker file persists across /clear so new sessions can see what was running.
Memory inject hook reads this file to inform new Claude about active/completed agents.
"""
import json
import os
import sys
import time
from pathlib import Path

TRACKER_FILE = Path("/tmp/claude_agent_tracker.json")
MAX_PROMPT_SNIPPET = 150
MAX_AGENTS = 20  # keep last N entries
STALE_HOURS = 2  # remove entries older than this


def _load():
    if TRACKER_FILE.exists():
        try:
            return json.loads(TRACKER_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"agents": []}


def _save(data):
    # Prune stale entries
    cutoff = time.time() - STALE_HOURS * 3600
    data["agents"] = [a for a in data["agents"] if a.get("started", 0) > cutoff]
    # Keep only last N
    data["agents"] = data["agents"][-MAX_AGENTS:]
    tmp = TRACKER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(TRACKER_FILE)


def _handle_spawn(input_data):
    """PreToolUse Agent: log new background agent."""
    tool_input = input_data.get("tool_input", {})

    # Only track background agents
    if not tool_input.get("run_in_background"):
        print("{}")
        return

    desc = tool_input.get("description", "unknown task")
    prompt = tool_input.get("prompt", "")[:MAX_PROMPT_SNIPPET]
    model = tool_input.get("model", "default")

    data = _load()
    data["agents"].append({
        "description": desc,
        "prompt_snippet": prompt,
        "model": model,
        "started": time.time(),
        "status": "running",
        "tty": os.environ.get("CLAUDE_TTY_ID", "?"),
    })
    _save(data)
    print("{}")


def _handle_stop(input_data):
    """SubagentStop: mark most recent matching agent as done."""
    data = _load()

    # Mark the oldest "running" agent as completed
    # (SubagentStop doesn't give us much to match on, so FIFO)
    for agent in data["agents"]:
        if agent.get("status") == "running":
            agent["status"] = "completed"
            agent["finished"] = time.time()
            break

    _save(data)
    print("{}")


def get_active_agents():
    """Called by memory inject hook to get context about recent agents."""
    data = _load()
    if not data["agents"]:
        return None

    lines = []
    for a in data["agents"]:
        status = a.get("status", "?")
        desc = a.get("description", "?")
        elapsed = time.time() - a.get("started", time.time())
        mins = int(elapsed / 60)

        if status == "running":
            lines.append(f"  - RUNNING ({mins}m): {desc} — {a.get('prompt_snippet', '')}")
        elif status == "completed":
            lines.append(f"  - DONE ({mins}m ago): {desc}")

    if not lines:
        return None

    return "Background agents from previous context:\n" + "\n".join(lines)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    # Detect mode
    tool_name = input_data.get("tool_name", "")

    if tool_name == "Agent":
        _handle_spawn(input_data)
    else:
        # SubagentStop mode (no tool_name, or different format)
        _handle_stop(input_data)


if __name__ == "__main__":
    main()
