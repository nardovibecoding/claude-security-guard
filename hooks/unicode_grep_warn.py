#!/usr/bin/env python3
# @bigd-hook-meta
# name: unicode_grep_warn
# fires_on: PreToolUse
# always_fire: true
# cost_score: 1
"""PreToolUse hook: warn to also search unicode escapes when grepping CJK characters."""
import json
import re
import sys


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name not in ("Bash", "Grep"):
        print("{}")
        return

    # Check for CJK characters in the search pattern/command
    search_text = tool_input.get("command", "") or tool_input.get("pattern", "")
    if not re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', search_text):
        print("{}")
        return

    print(json.dumps({
        "systemMessage": (
            "⚠️ **CJK grep detected.** Also search unicode escapes (`\\uXXXX`) — "
            "some files store Chinese text as escaped unicode, not raw UTF-8."
        )
    }))


if __name__ == "__main__":
    main()
