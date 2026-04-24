#!/usr/bin/env python3
# @bigd-hook-meta
# name: reasoning_leak_canary
# fires_on: PostToolUse
# relevant_intents: [code, debug, telegram]
# irrelevant_intents: [bigd, pm, docx, x_tweet, git, vps, sync, memory]
# cost_score: 1
# always_fire: false
"""PostToolUse hook: after editing prompt/outreach files, warn about reasoning leak risk."""
import io
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# Files that contain system prompts or outreach logic
PROMPT_PATTERNS = [
    "system_prompt",
    "outreach/",
    "auto_reply",
    "few_shot",
    "prompt_template",
    "persona_prompt",
]


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return any(p in file_path for p in PROMPT_PATTERNS)


def action(tool_name, tool_input, input_data):
    return (
        "⚠️ **Prompt/outreach file edited.** Reasoning leak risk.\n"
        "Before deploying, test with a canary message and verify:\n"
        "1. No `<think>` tags in output\n"
        "2. No `let me follow the rules` or similar CoT leaks\n"
        "3. No meta-commentary about the prompt itself\n"
        "Run the red team subset: `python red_team_chain.py --quick`"
    )


if __name__ == "__main__":
    _raw = sys.stdin.read()
    try:
        _prompt = json.loads(_raw).get("prompt", "") if _raw else ""
    except Exception:
        _prompt = ""
    from _semantic_router import should_fire
    if not should_fire(__file__, _prompt):
        print("{}")
        sys.exit(0)
    sys.stdin = io.StringIO(_raw)
    run_hook(check, action, "reasoning_leak_canary")
