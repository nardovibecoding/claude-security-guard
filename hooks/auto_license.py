#!/usr/bin/env python3
# @bigd-hook-meta
# name: auto_license
# fires_on: PostToolUse
# relevant_intents: [git, code]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, vps, sync, memory, debug]
# cost_score: 2
# always_fire: false
"""PostToolUse hook: after gh repo create → auto-setup all mechanical parts + prompt all writing parts."""
import io
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook


def check(tool_name, tool_input, input_data):
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(re.search(r"gh\s+repo\s+create", cmd))


def action(tool_name, tool_input, input_data):
    cwd = input_data.get("cwd", str(Path.cwd()))
    done = []
    todo = []

    # --- MECHANICAL (auto-do) ---

    # 1. LICENSE
    license_path = Path(cwd) / "LICENSE"
    if not license_path.exists():
        try:
            header = "Copyright (c) 2026 Nardo (<github-user>)\n\n"
            result = subprocess.run(
                ["curl", "-sL", "https://www.gnu.org/licenses/agpl-3.0.txt"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                license_path.write_text(header + result.stdout)
                done.append("✅ LICENSE (AGPL-3.0)")
        except Exception:
            todo.append("⚠️ LICENSE — curl failed, add manually")
    else:
        done.append("✅ LICENSE (already exists)")

    # 2. .gitignore
    gitignore_path = Path(cwd) / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "__pycache__/\n*.pyc\n.venv/\nvenv/\n.env\n*.egg-info/\n"
            "dist/\nbuild/\n.DS_Store\nnode_modules/\n"
        )
        done.append("✅ .gitignore")
    else:
        done.append("✅ .gitignore (already exists)")

    # 3. NOTICE
    notice_path = Path(cwd) / "NOTICE"
    if not notice_path.exists():
        notice_path.write_text(
            "This project is maintained by Nardo (@<github-user>).\n"
            "Licensed under AGPL-3.0. See LICENSE for details.\n"
        )
        done.append("✅ NOTICE")

    # --- WRITING NEEDED (prompt Claude) ---
    readme_path = Path(cwd) / "README.md"
    if not readme_path.exists():
        todo.append("📝 README.md — call `github_readme_sync` for tables, then write: header, description, install, usage, built-with")

    todo.append("📝 Repo description — call `github_metadata` with action='set', write a compelling one-liner")
    todo.append("📝 Topics — call `github_metadata` with topics list (claude-code, mcp, etc.)")
    todo.append("📝 CHANGELOG — call `github_changelog` for git log data, write a summary")
    todo.append("📝 Badges — use badge_text from `github_readme_sync` in README header")

    # --- FORMAT ---
    msg = "**🚀 New repo created — auto-setup complete:**\n"
    msg += "\n".join(done)
    msg += "\n\n**Still needed (call MCP tools + write):**\n"
    msg += "\n".join(todo)
    msg += "\n\nAfter all done: `git add -A && git commit -m 'initial setup' && git push`"

    return msg


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
    run_hook(check, action, "auto_license")
