#!/usr/bin/env python3
"""PreToolUse hook: warn to send QR codes as document not photo on Telegram."""
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

    # Check for TG reply tool with QR image
    if "telegram" not in tool_name and "reply" not in tool_name:
        print("{}")
        return

    files = tool_input.get("files", [])
    if not files:
        print("{}")
        return

    has_qr = any(
        re.search(r'qr|login|scan', str(f), re.IGNORECASE)
        for f in files
    )

    if has_qr:
        print(json.dumps({
            "systemMessage": (
                "⚠️ **QR code detected.** Send as document (not photo) on Telegram — "
                "photo compression can make QR codes unscannable."
            )
        }))
    else:
        print("{}")


if __name__ == "__main__":
    main()
