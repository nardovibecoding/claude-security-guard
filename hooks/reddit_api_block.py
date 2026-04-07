#!/usr/bin/env python3
"""PostToolUse hook: block Reddit OAuth API usage — Reddit API is dead, use scraping."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    content = tool_input.get("new_string", "") or tool_input.get("content", "")
    return bool(re.search(
        r"REDDIT_CLIENT_ID|REDDIT_CLIENT_SECRET|praw\.Reddit\(|"
        r"reddit_client_id|reddit_client_secret",
        content
    ))


def action(tool_name, tool_input, input_data):
    return (
        "⛔ **Reddit OAuth API is dead.** Do not use REDDIT_CLIENT_ID/SECRET or praw. "
        "Reddit revoked free API access. Use web scraping (fetch_watchdog probes) instead."
    )


if __name__ == "__main__":
    run_hook(check, action, "reddit_api_block")
