#!/usr/bin/env python3
# @bigd-hook-meta
# name: auto_skill_sync
# fires_on: PostToolUse
# relevant_intents: [meta, code]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, git, vps, sync, memory, debug]
# cost_score: 2
# always_fire: false
"""PostToolUse hook: sync public skills to claude-skills-curation, remind VPS sync for private."""
import io
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

PUBLIC_REPO = Path.home() / "claude-skills-curation/skills"

# Sanitization: strip private paths before writing to public repo
_STRIP = [
    (re.compile(r"~/telegram-claude-bot/"), "./"),
    (re.compile(r"~/"), "~/"),
    (re.compile(r"~/"), "~/"),
    (re.compile(r"bernard@157\.180\.28\.14"), "<user>@<vps-ip>"),
    (re.compile(r"~/.claude/projects/[^\s/]+/memory/"), "~/.claude/projects/*/memory/"),
]

def _sanitize(content: str) -> str:
    for pattern, replacement in _STRIP:
        content = pattern.sub(replacement, content)
    return content

def _find_public(skill_name: str) -> Path | None:
    for p in PUBLIC_REPO.rglob("SKILL.md"):
        if p.parent.name == skill_name:
            return p
    return None

def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return bool(re.search(r"\.claude/skills/.*SKILL\.md", file_path))

def action(tool_name, tool_input, input_data):
    file_path = Path(tool_input.get("file_path", ""))
    skill_name = file_path.parent.name
    public_dest = _find_public(skill_name)

    if public_dest:
        content = _sanitize(file_path.read_text())
        public_dest.write_text(content)
        result = subprocess.run(
            f'cd ~/claude-skills-curation && git add skills && git commit -m "skill update: {skill_name}" && git push',
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            return f"Public skill '{skill_name}' synced to claude-skills-curation."
        else:
            return f"Public skill '{skill_name}' copied but git push failed: {result.stderr.strip()}"
    else:
        return f"Private skill. Sync to VPS: `cd ~/.claude/skills && git add -A && git commit -m 'skill update' && git push`"

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
    run_hook(check, action, "auto_skill_sync")
