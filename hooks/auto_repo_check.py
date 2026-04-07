#!/usr/bin/env python3
"""PostToolUse hook: after git push to public repos → remind to check README/description sync."""
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook


# Auto-detect: any repo under nardovibecoding is public and should have up-to-date READMEs
# No hardcoded list — checks the git remote URL instead
PUBLIC_ORG = "nardovibecoding"


def check(tool_name, tool_input, input_data):
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(re.search(r"git\s+push", cmd))


def action(tool_name, tool_input, input_data):
    cwd = input_data.get("cwd", "")

    # Detect which repo we pushed to
    try:
        result = subprocess.run(
            ["git", "-C", cwd or ".", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        remote_url = result.stdout.strip()
    except Exception:
        return None

    # Check if it's one of our public repos (any repo under nardovibecoding)
    if PUBLIC_ORG not in remote_url:
        return None  # Not our org, skip

    # Extract repo name from URL
    repo_name = remote_url.rstrip("/").split("/")[-1].replace(".git", "")

    # Check if README exists and has recent changes
    readme = Path(cwd or ".") / "README.md"
    if not readme.exists():
        return f"📋 **Pushed to public repo {repo_name}** but no README.md found. Write one using `github_readme_sync` for tables."

    # Check what was pushed — if any SKILL.md, hooks, or server.py changed, README might be stale
    try:
        result = subprocess.run(
            ["git", "-C", cwd or ".", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        changed = result.stdout.strip().splitlines()
    except Exception:
        changed = []

    stale_triggers = ["SKILL.md", "server.py", "hooks/", "patterns.py", "pyproject.toml"]
    stale_files = [f for f in changed if any(t in f for t in stale_triggers)]

    if stale_files and "README.md" not in changed:
        return (
            f"📋 **Pushed to {repo_name}** — these changes may affect README:\n"
            f"{', '.join(stale_files[:5])}\n"
            f"Call `repo_sync_check` to verify, then update README if needed."
        )

    return None


if __name__ == "__main__":
    run_hook(check, action, "auto_repo_check")
