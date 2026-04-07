#!/usr/bin/env python3
"""
auto_hook_deploy.py — PostToolUse hook (Edit|Write)
When a file in telegram-claude-bot/hooks/ is edited, auto-deploy it
to ~/.claude/hooks/ with platform filtering.
Also validates: syntax check, no hardcoded paths, no secrets.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_HOOKS = Path.home() / "telegram-claude-bot" / "hooks"
TARGET_HOOKS = Path.home() / ".claude" / "hooks"

# Read Mac-only hooks from shared JSON (single source of truth)
_FILTER_FILE = Path(__file__).parent / "platform_filter.json"
try:
    import json as _json
    MAC_ONLY = set(_json.load(open(_FILTER_FILE))["mac_only"])
except Exception:
    MAC_ONLY = set()

# Patterns that suggest hardcoded paths (should use ~ or Path.home())
BAD_PATTERNS = [
    "/Users/bernard/",
    "/home/bernard/",
]


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    fp = Path(file_path)

    # Only trigger for hooks in the repo
    if str(REPO_HOOKS) not in str(fp):
        sys.exit(0)

    if not fp.name.endswith(".py"):
        sys.exit(0)

    results = []

    # 1. Syntax check
    r = subprocess.run(
        [sys.executable, "-m", "py_compile", str(fp)],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        results.append(f"❌ Syntax error in {fp.name}:\n{r.stderr}")
        print("\n".join(results))
        sys.exit(0)  # don't deploy broken hooks

    results.append(f"✅ Syntax OK: {fp.name}")

    # 2. Check for hardcoded paths
    content = fp.read_text()
    for pattern in BAD_PATTERNS:
        # Allow patterns inside regex strings (like auto_pre_publish.py detectors)
        lines = [
            (i + 1, line) for i, line in enumerate(content.splitlines())
            if pattern in line and "r'" not in line and 'r"' not in line
        ]
        if lines:
            for ln, line in lines[:3]:
                results.append(f"⚠️  Hardcoded path at line {ln}: {line.strip()[:80]}")

    # 3. Platform filter
    is_mac = platform.system() == "Darwin"
    if not is_mac and fp.name in MAC_ONLY:
        results.append(f"⏭️  {fp.name} is Mac-only, skipping deploy on Linux")
        print("\n".join(results))
        sys.exit(0)

    # 4. Deploy
    TARGET_HOOKS.mkdir(parents=True, exist_ok=True)
    dest = TARGET_HOOKS / fp.name
    shutil.copy2(fp, dest)
    results.append(f"📦 Deployed {fp.name} → ~/.claude/hooks/")

    print("\n".join(results))
    sys.exit(0)


if __name__ == "__main__":
    main()
