#!/usr/bin/env python3
"""PostToolUse hook: grep for references after file move/delete."""
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook


def check(tool_name, tool_input, input_data):
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(re.search(r"\b(mv|rm|git\s+rm)\b", cmd))


def action(tool_name, tool_input, input_data):
    cmd = tool_input.get("command", "")
    # Extract file paths from mv/rm commands
    # Simple heuristic: last argument(s) that look like file paths
    parts = cmd.split()
    files = [p for p in parts if "/" in p or "." in p and not p.startswith("-")]
    if not files:
        return None

    target = files[-1]
    basename = Path(target).name
    if not basename or basename in (".", ".."):
        return None

    # Grep for references in common locations
    search_dirs = [
        str(Path.home() / "telegram-claude-bot"),
        str(Path.home() / ".claude"),
    ]
    refs = []
    for search_dir in search_dirs:
        try:
            result = subprocess.run(
                ["grep", "-rl", basename, search_dir,
                 "--include=*.py", "--include=*.md", "--include=*.json",
                 "--include=*.sh", "--include=*.yaml"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                refs.extend(result.stdout.strip().splitlines()[:10])
        except (subprocess.TimeoutExpired, Exception):
            continue

    if refs:
        ref_list = "\n".join(f"  - {r}" for r in refs[:10])
        return f"File `{basename}` is referenced in {len(refs)} files:\n{ref_list}\nCheck these before proceeding."
    return None


if __name__ == "__main__":
    run_hook(check, action, "auto_dependency_grep")
