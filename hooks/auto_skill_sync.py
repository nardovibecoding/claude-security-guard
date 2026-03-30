#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PostToolUse hook: remind to sync skills after SKILL.md edit."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return bool(re.search(r"\.claude/skills/.*SKILL\.md$", file_path))


def action(tool_name, tool_input, input_data):
    return "Skill file modified. Sync to VPS: `cd ~/.claude/skills && git add -A && git commit -m 'skill update' && git push`"


if __name__ == "__main__":
    run_hook(check, action, "auto_skill_sync")
