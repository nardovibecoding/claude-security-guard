#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""SessionStart hook: check MCP server health and cookie freshness on VPS."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vps_config import VPS_SSH


def ssh_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", VPS_SSH, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def main():
    alerts = []

    # Check XHS MCP service
    ok, out = ssh_cmd("systemctl --user is-active xhs-mcp 2>&1")
    if not ok or "active" not in out:
        alerts.append("⚠️ **XHS MCP** is not running on VPS")
    else:
        # Check restart count — crash-looping detection
        ok2, restarts = ssh_cmd(
            "systemctl --user show xhs-mcp -p NRestarts --value 2>&1"
        )
        if ok2 and restarts.isdigit() and int(restarts) > 100:
            alerts.append(f"⚠️ **XHS MCP** crash-looping: {restarts} restarts")

    # Check Douyin MCP service
    ok, out = ssh_cmd("systemctl --user is-active douyin-mcp 2>&1")
    if not ok or "active" not in out:
        alerts.append("⚠️ **Douyin MCP** is not running on VPS")

    # Check cookie freshness
    ok, out = ssh_cmd(
        "find ~/telegram-claude-bot -name '*cookie*' -mtime +7 -type f 2>/dev/null | head -5"
    )
    if ok and out:
        stale = out.count("\n") + 1
        alerts.append(f"⚠️ **{stale} cookie file(s)** older than 7 days — may need refresh")

    if alerts:
        msg = "**Session health check:**\n" + "\n".join(alerts)
        print(json.dumps({"systemMessage": msg}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
