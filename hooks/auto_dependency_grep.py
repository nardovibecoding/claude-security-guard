#!/usr/bin/env python3
"""PostToolUse hook: dependency tracking for file moves AND content edits.

Two modes:
1. Bash mv/rm/git rm → grep for references to the moved/deleted file
2. Edit/Write on source-of-truth files → warn about downstream files

The dependency map is the single source of truth for what depends on what.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

_HOME = str(Path.home())
_PROJECT = Path.home() / "telegram-claude-bot"

# Source-of-truth files → downstream files that may need updating
# When a source file is edited, warn about its dependents
_DEPENDENCY_MAP = {
    # Core config → docs + commands
    "llm_client.py": [
        "ADMIN_HANDBOOK.md", "TERMINAL_MEMORY.md",
        "settings.template.json",
        "admin_bot/commands.py (/config, /version, /panel)",
    ],
    "config.py": [
        "ADMIN_HANDBOOK.md", "TERMINAL_MEMORY.md",
        "admin_bot/commands.py", "admin_bot/callbacks.py",
        "admin_bot/domains.py", "admin_bot/schedulers.py",
        "memory/project_telegram_bot.md",
    ],
    "start_all.sh": [
        "ADMIN_HANDBOOK.md", "TERMINAL_MEMORY.md",
        "skills/add-persona/SKILL.md",
    ],
    "bot_base.py": [
        "ADMIN_HANDBOOK.md", "TERMINAL_MEMORY.md",
    ],
    ".env": [
        "memory/reference_api_keys_locations.md",
        "hooks/vps_config.py (VPS_HOST, VPS_USER)",
    ],
    "requirements.txt": [
        "VPS pip install (auto_pip_install.py handles this)",
    ],
    # Shared modules — wide blast radius
    "sanitizer.py": [
        "13 importers — any change affects all bots + bridge + digests",
    ],
    "utils.py": [
        "10+ importers — bot_base, bridge, all digest scripts",
    ],
    "memory.py": [
        "bot_base.py (only importer)",
        "memory/project_telegram_bot.md",
    ],
    # Persona configs
    "daliu.json": ["memory/project_personas.md", "CLAUDE.md"],
    "sbf.json": ["memory/project_personas.md", "CLAUDE.md"],
    "twitter.json": ["memory/project_personas.md", "CLAUDE.md"],
    "xcn.json": ["memory/project_personas.md", "CLAUDE.md"],
    "xai.json": ["memory/project_personas.md", "CLAUDE.md"],
    "xniche.json": ["memory/project_personas.md", "CLAUDE.md"],
    "reddit.json": ["memory/project_personas.md", "CLAUDE.md"],
    # Rules + hooks
    "CLAUDE.md": [
        "admin_bot/config.py (_BASE_PROMPT references rules)",
        "ADMIN_HANDBOOK.md (may duplicate content)",
        "TERMINAL_MEMORY.md",
    ],
    "deploy_hooks.sh": [
        "hooks/auto_hook_deploy.py (MAC_ONLY list must match)",
        "memory/project_sync_workflow.md",
    ],
    "hook_base.py": [
        "All 30+ hooks import from this — test before deploying",
    ],
    "vps_config.py": [
        "hooks/auto_vps_sync.py", "hooks/auto_pip_install.py",
        "hooks/cookie_health.py", "hooks/cron_log_monitor.py",
    ],
    # Runtime config
    "domain_groups.json": [
        "admin_bot/domains.py", "admin_bot/commands.py",
    ],
    "xlist_config.json": [
        "x_curator.py", "admin_bot/schedulers.py",
    ],
    ".gitignore": [
        "memory/reference_api_keys_locations.md",
    ],
    # Public repo sync — hooks that publish to claude-security-guard
    "guard_safety.py": [
        "PUBLIC: claude-security-guard — run sync_public_repos.py",
    ],
    "auto_test_after_edit.py": [
        "PUBLIC: claude-security-guard — run sync_public_repos.py",
    ],
    "auto_review_before_done.py": [
        "PUBLIC: claude-security-guard — run sync_public_repos.py",
    ],
    # Content — never hardcode repo stats in memory/tweets
    "sync_public_repos.py": [
        "memory/reference_github_repos.md (don't hardcode counts)",
        "memory/project_ops_guard_plugin.md (don't hardcode counts)",
        "content_drafts/ (check queued tweets for stale numbers)",
    ],
}


def check(tool_name, tool_input, _input_data):
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return bool(re.search(r"\b(mv|rm|git\s+rm)\b", cmd))
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "")
        fname = Path(fp).name if fp else ""
        return fname in _DEPENDENCY_MAP
    return False


def action(tool_name, tool_input, _input_data):
    # Mode 1: File move/delete — grep for references
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        parts = cmd.split()
        files = [p for p in parts
                 if ("/" in p or "." in p) and not p.startswith("-")]
        if not files:
            return None

        target = files[-1]
        basename = Path(target).name
        if not basename or basename in (".", ".."):
            return None

        search_dirs = [
            str(Path.home() / "telegram-claude-bot"),
            str(Path.home() / ".claude"),
        ]
        refs = []
        for search_dir in search_dirs:
            try:
                result = subprocess.run(
                    ["grep", "-rl", basename, search_dir,
                     "--include=*.py", "--include=*.md",
                     "--include=*.json", "--include=*.sh",
                     "--include=*.yaml"],
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip():
                    refs.extend(result.stdout.strip().splitlines()[:10])
            except (subprocess.TimeoutExpired, Exception):
                continue

        if refs:
            ref_list = "\n".join(f"  - {r}" for r in refs[:10])
            return (
                f"File `{basename}` is referenced in "
                f"{len(refs)} files:\n{ref_list}\n"
                f"Check these before proceeding."
            )
        return None

    # Mode 2: Edit/Write on source-of-truth file — warn about deps
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "")
        fname = Path(fp).name if fp else ""
        deps = _DEPENDENCY_MAP.get(fname)
        if not deps:
            return None
        dep_list = "\n".join(f"  - {d}" for d in deps)
        return (
            f"DEPENDENCY: `{fname}` is a source-of-truth file. "
            f"Check these for stale references:\n{dep_list}"
        )

    return None


if __name__ == "__main__":
    run_hook(check, action, "auto_dependency_grep")
