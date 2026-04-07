#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PostToolUse hook: dependency tracking for file moves AND content edits.

Four modes:
1. Bash mv/rm/git rm → grep for references to the moved/deleted file
2. Edit/Write on source-of-truth files → warn about downstream files (blocking)
3. Edit/Write any file → auto constant-value grep, log to /tmp/dep_value_grep.log (non-blocking)
4. Edit/Write public-repo files → warn about cross-repo propagation (blocking)
"""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

_HOME = str(Path.home())
_PROJECT = Path.home() / "telegram-claude-bot"
_DEP_VALUE_LOG = "/tmp/dep_value_grep.log"

# Files in sync_public_repos.py SYNC_MAP → which public repos they sync to
_CROSS_REPO_MAP = {
    # claude-sec-ops-guard + others
    "guard_safety.py":            ["claude-sec-ops-guard", "claude-skills-curation"],
    "hook_base.py":               ["claude-sec-ops-guard", "claude-quality-gate", "claude-skills-curation"],
    "test_helpers.py":            ["claude-sec-ops-guard", "claude-quality-gate"],
    "auto_copyright_header.py":   ["claude-sec-ops-guard", "claude-quality-gate"],
    "auto_license.py":            ["claude-sec-ops-guard", "claude-quality-gate"],
    "auto_repo_check.py":         ["claude-sec-ops-guard"],
    "auto_pre_publish.py":        ["claude-sec-ops-guard"],
    "auto_hook_deploy.py":        ["claude-sec-ops-guard"],
    "auto_skill_sync.py":         ["claude-sec-ops-guard", "claude-skills-curation"],
    "auto_dependency_grep.py":    ["claude-sec-ops-guard", "claude-skills-curation"],
    "auto_test_after_edit.py":    ["claude-sec-ops-guard", "claude-quality-gate"],
    "auto_review_before_done.py": ["claude-sec-ops-guard", "claude-quality-gate"],
    "verify_infra.py":            ["claude-sec-ops-guard"],
    "pre_commit_validate.py":     ["claude-sec-ops-guard", "claude-quality-gate"],
    "reasoning_leak_canary.py":   ["claude-sec-ops-guard"],
    "skill_disable_not_delete.py":["claude-sec-ops-guard"],
    "unicode_grep_warn.py":       ["claude-sec-ops-guard", "claude-quality-gate"],
    # claude-quality-gate only
    "async_safety_guard.py":      ["claude-quality-gate"],
    "resource_leak_guard.py":     ["claude-quality-gate"],
    "hardcoded_model_guard.py":   ["claude-quality-gate"],
    "tg_security_guard.py":       ["claude-quality-gate"],
    "tg_api_guard.py":            ["claude-quality-gate"],
    "admin_only_guard.py":        ["claude-quality-gate"],
    "temp_file_guard.py":         ["claude-quality-gate"],
    # claude-skills-curation
    "auto_vps_sync.py":           ["claude-skills-curation"],
    "auto_memory_index.py":       ["claude-skills-curation"],
    "auto_pip_install.py":        ["claude-skills-curation"],
    "auto_content_remind.py":     ["claude-skills-curation"],
    "auto_restart_process.py":    ["claude-skills-curation"],
    "auto_bot_restart.py":        ["claude-skills-curation"],
    # claude-social-pipeline
    "tweet_stats.py":             ["claude-social-pipeline"],
}

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
    # Digest routing — changing chat_id/thread_id affects config.py + memory
    "youtube_digest.py": [
        "admin_bot/config.py (PERSONAL_THREADS — remove old thread if moved)",
        "memory/project_ai_digest.md",
    ],
    "podcast_digest.py": [
        "admin_bot/config.py (PERSONAL_THREADS — remove old thread if moved)",
        "memory/project_ai_digest.md",
    ],
    # Content — never hardcode repo stats in memory/tweets
    "sync_public_repos.py": [
        "memory/reference_github_repos.md (don't hardcode counts)",
        "memory/project_ops_guard_plugin.md (don't hardcode counts)",
        "content_drafts/ (check queued tweets for stale numbers)",
    ],
}


def _value_grep_log(fname: str, content: str) -> None:
    """Mode 3: Extract Telegram IDs and thread constants, grep project, log hits."""
    try:
        values = set()
        # Telegram group/channel IDs (negative 13-digit numbers)
        values.update(re.findall(r'-100\d{10,13}', content))
        # Thread/topic ID assignments: THREAD_ID = 123, YOUTUBE_THREAD = 156, etc.
        for m in re.finditer(
            r'(?:THREAD|TOPIC|GROUP_ID|CHAT_ID|FORUM)[_A-Z0-9]*\s*=\s*(-?\d+)',
            content
        ):
            values.add(m.group(1))
        if not values:
            return
        search_dirs = [
            str(Path.home() / "telegram-claude-bot"),
            str(Path.home() / ".claude" / "hooks"),
        ]
        ts = datetime.now().strftime("%H:%M")
        for val in sorted(values):
            hits = []
            for d in search_dirs:
                try:
                    r = subprocess.run(
                        ["grep", "-rl", val, d,
                         "--include=*.py", "--include=*.json"],
                        capture_output=True, text=True, timeout=3
                    )
                    hits.extend(r.stdout.strip().splitlines())
                except Exception:
                    pass
            # Only log if value appears in 2+ distinct files
            unique = sorted(set(hits))
            if len(unique) >= 2:
                files_str = ", ".join(unique[:8])
                with open(_DEP_VALUE_LOG, "a") as f:
                    f.write(f"[{ts}] {fname}: {val} → {files_str}\n")
    except Exception:
        pass  # never break the hook


def check(tool_name, tool_input, _input_data):
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return bool(re.search(r"\b(mv|rm|git\s+rm)\b", cmd))
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "")
        return bool(fp)  # always fire — action() decides what to return
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
            n = len(refs)
            tier = "CRITICAL" if n >= 10 else "HIGH" if n >= 4 else "LOW"
            return (
                f"[{tier}] File `{basename}` is referenced in "
                f"{n} files:\n{ref_list}\n"
                f"Check these before proceeding."
            )
        return None

    # Modes 2, 3, 4: Edit/Write
    if tool_name in ("Edit", "Write"):
        fp = tool_input.get("file_path", "")
        fname = Path(fp).name if fp else ""

        # Mode 3: always run value-grep as non-blocking side-effect
        new_content = tool_input.get("new_string", "") or tool_input.get("content", "")
        _value_grep_log(fname, new_content)

        msgs = []

        # Mode 2: source-of-truth dependency map (blocking)
        deps = _DEPENDENCY_MAP.get(fname)
        if deps:
            dep_list = "\n".join(f"  - {d}" for d in deps)
            msgs.append(
                f"DEPENDENCY: `{fname}` is a source-of-truth file. "
                f"Check these for stale references:\n{dep_list}"
            )

        # Mode 4: cross-repo sync warning (blocking)
        repos = _CROSS_REPO_MAP.get(fname)
        if repos:
            msgs.append(
                f"CROSS-REPO: `{fname}` → {', '.join(repos)} — will sync on next push"
            )

        return "\n\n".join(msgs) if msgs else None

    return None


if __name__ == "__main__":
    run_hook(check, action, "auto_dependency_grep")
