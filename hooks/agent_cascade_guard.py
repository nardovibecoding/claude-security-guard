#!/usr/bin/env python3
"""PreToolUse hook: prevent agent cascade (agents spawning agents).
Checks CLAUDE_AGENT_DEPTH env var and session context to detect sub-agent spawns."""
import json
import os
import sys


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    if input_data.get("tool_name") != "Agent":
        print("{}")
        return

    # Check if we're already inside a subagent
    # Claude Code sets this env var for subagents
    agent_depth = int(os.environ.get("CLAUDE_AGENT_DEPTH", "0"))
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    parent_id = os.environ.get("CLAUDE_PARENT_SESSION_ID", "")

    # If parent session exists, we're a subagent -- block further spawning
    if parent_id or agent_depth > 0:
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "BLOCKED: Agent cascade detected. You are already a subagent -- do NOT spawn further agents. Use Bash, Read, Grep, Glob directly.",
                "additionalContext": "You are running inside a subagent (depth={depth}). Spawning another agent wastes tokens exponentially. Use direct tools: Bash, Read, Grep, Glob, WebFetch.".format(depth=agent_depth),
            }
        }
        print(json.dumps(result))
        return

    print("{}")


if __name__ == "__main__":
    main()
