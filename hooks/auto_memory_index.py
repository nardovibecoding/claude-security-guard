#!/usr/bin/env python3
"""PostToolUse hook: check if new memory file is in MEMORY.md index."""
import sys
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook

MEMORY_DIR = Path.home() / ".claude/projects/-Users-bernard/memory"
INDEX = MEMORY_DIR / "MEMORY.md"


def check(tool_name, tool_input, input_data):
    if tool_name != "Write":
        return False
    file_path = tool_input.get("file_path", "")
    return (
        "memory/" in file_path
        and file_path.endswith(".md")
        and "MEMORY.md" not in file_path
    )


def action(tool_name, tool_input, input_data):
    file_path = tool_input.get("file_path", "")
    filename = Path(file_path).name
    if not INDEX.exists():
        return None
    index_content = INDEX.read_text()
    if filename in index_content:
        return None  # Already indexed
    return f"New memory file `{filename}` is NOT in MEMORY.md index. Add it."


if __name__ == "__main__":
    run_hook(check, action, "auto_memory_index")
