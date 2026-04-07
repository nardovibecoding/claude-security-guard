#!/usr/bin/env python3
"""PreToolUse hook: default all agents to Haiku unless task needs Sonnet+.
Rule: everything is Haiku unless explicitly complex (r1a, implement, debug, refactor)."""
import json
import sys
import re

# ONLY these patterns justify Sonnet/Opus agent
NEEDS_SONNET = [
    r"\br1a\b",
    r"implement\b", r"refactor\b", r"rewrite\b",
    r"build (?:a |the |this )",
    r"write (?:code|the implementation|a full)",
    r"fix (?:the |this )?bug",
    r"debug\b", r"architect\b", r"redesign\b",
    r"migrate\b", r"port (?:to|from)\b",
    r"security (?:audit|review)",
    r"review (?:and fix|all|the code)",
    r"plan (?:the|how to) implement",
    r"multi.?step",
]


def requires_sonnet(prompt, model_override):
    if model_override == "opus":
        return True
    prompt_lower = prompt.lower().strip()
    for pat in NEEDS_SONNET:
        if re.search(pat, prompt_lower):
            return True
    return False


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    if input_data.get("tool_name") != "Agent":
        print("{}")
        return

    tool_input = input_data.get("tool_input", {})
    prompt = tool_input.get("prompt", "")
    model_override = tool_input.get("model", "")
    description = tool_input.get("description", "").lower()

    # Skip background auto-save/wiki agents
    if tool_input.get("run_in_background") is True:
        if any(kw in description for kw in ["save", "memory", "wiki", "librarian", "filing"]):
            print("{}")
            return

    # Already haiku → fine
    if model_override == "haiku":
        print("{}")
        return

    # Complex task → allow sonnet/opus
    if requires_sonnet(prompt, model_override):
        print("{}")
        return

    # Everything else → nudge haiku
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": 'TOKEN SAVE: Use model: "haiku" for this agent. Only use Sonnet for code writing, debugging, or r1a research.',
        }
    }))


if __name__ == "__main__":
    main()
