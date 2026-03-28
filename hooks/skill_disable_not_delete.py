#!/usr/bin/env python3
"""PreToolUse hook: warn to rename SKILL.md to .disabled instead of deleting."""
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

    if tool_name != "Bash":
        print("{}")
        return

    cmd = tool_input.get("command", "")

    # Detect rm of SKILL.md or entire skill directory
    if re.search(r'rm\s+.*SKILL\.md|rm\s+-r.*skills/', cmd):
        print(json.dumps({
            "systemMessage": (
                "⚠️ **Don't delete skills.** Rename to `.disabled` instead:\n"
                "`mv SKILL.md SKILL.md.disabled`\n"
                "This preserves the skill for future re-enable. Only delete if permanently replaced."
            )
        }))
        return

    print("{}")


if __name__ == "__main__":
    main()
