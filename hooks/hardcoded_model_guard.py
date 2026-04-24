#!/usr/bin/env python3
# @bigd-hook-meta
# name: hardcoded_model_guard
# fires_on: PostToolUse
# relevant_intents: [code, meta, debug]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, vps, sync, memory]
# cost_score: 2
# always_fire: false
# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""PostToolUse hook: block hardcoded model name strings in Python files.

Catches:
- Hardcoded "MiniMax-M2.5", "MiniMax-M2.7", "llama-3.3-70b" etc. in non-llm_client.py files
- Rationale: all model names must live in llm_client.py PROVIDERS dict (CLAUDE.md rule)

Commits this prevents: 09276b4, 479aa24, ff1bd59, 51d6b80, e21bbdc
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# Model name strings that must only appear in llm_client.py
_MODEL_PATTERNS = [
    r'"MiniMax-M2\.[0-9]',
    r"'MiniMax-M2\.[0-9]",
    r'"MiniMax-Text-01',
    r"'MiniMax-Text-01",
    r'"llama-3\.[0-9]+-[0-9]+b"',
    r"'llama-3\.[0-9]+-[0-9]+b'",
    r'"deepseek-chat"',
    r"'deepseek-chat'",
    r'"gemini-[0-9]',
    r"'gemini-[0-9]",
    r'"claude-[0-9]',
    r"'claude-[0-9]",
    r'"gpt-[0-9]',
    r"'gpt-[0-9]",
    # model= kwargs with hardcoded strings
    r'model\s*=\s*"(MiniMax|llama|deepseek|gemini|claude|gpt)',
    r"model\s*=\s*'(MiniMax|llama|deepseek|gemini|claude|gpt)",
]

_COMPILED = [re.compile(p) for p in _MODEL_PATTERNS]

# Files where hardcoded model names are legitimate
_ALLOWLIST = {
    "llm_client.py",
    "hardcoded_model_guard.py",
    "requirements.txt",
    ".md",
}


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    # Allow llm_client.py and this hook itself
    fname = Path(fp).name
    if fname in _ALLOWLIST:
        return False
    return True


def action(tool_name, tool_input, _input_data):
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    hits = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        # Skip comments and docstrings
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for pattern in _COMPILED:
            if pattern.search(stripped):
                hits.append(f"  line ~{i}: `{stripped[:80]}`")
                break

    if not hits:
        return None

    fp = tool_input.get("file_path", "")
    return (
        f"HARDCODED MODEL GUARD: model name literal in `{Path(fp).name}`.\n"
        "All model names must live in llm_client.py PROVIDERS dict (CLAUDE.md rule).\n"
        "Import the name via `from llm_client import PROVIDERS` or `get_primary_client()`.\n"
        + "\n".join(hits[:5])
    )


if __name__ == "__main__":
    import io
    import json
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
    run_hook(check, action, "hardcoded_model_guard")
