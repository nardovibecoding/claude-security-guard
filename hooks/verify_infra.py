#!/usr/bin/env python3
# @bigd-hook-meta
# name: verify_infra
# fires_on: PostToolUse
# relevant_intents: [vps, sync]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, git, code, memory, debug]
# cost_score: 2
# always_fire: false
"""PostToolUse hook: after crontab/systemctl setup, auto-verify on target."""
import io
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook, ssh_cmd


def check(tool_name, tool_input, input_data):
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(re.search(
        r"crontab\s+-e|crontab\s+.*<<|"
        r"systemctl\s+(enable|disable|daemon-reload|start|restart)\s|"
        r"systemctl\s+--user\s+(enable|disable|daemon-reload|start|restart)\s",
        cmd
    ))


def action(tool_name, tool_input, input_data):
    cmd = tool_input.get("command", "")

    if "systemctl" in cmd:
        # Extract service name
        match = re.search(r"systemctl\s+(?:--user\s+)?(?:enable|start|restart)\s+(\S+)", cmd)
        if match:
            service = match.group(1)
            user_flag = "--user " if "--user" in cmd else ""
            ok, out = ssh_cmd(f"systemctl {user_flag}status {service} 2>&1 | head -5")
            if ok:
                return f"✅ Verified on VPS: `{service}` is active.\n{out}"
            return f"⚠️ VPS verification: `{service}` may not be running:\n{out}"

    if "crontab" in cmd:
        ok, out = ssh_cmd("crontab -l 2>&1 | tail -5")
        if ok:
            return f"✅ VPS crontab verified. Last 5 entries:\n{out}"
        return f"⚠️ Could not verify VPS crontab: {out}"

    return None


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
    run_hook(check, action, "verify_infra")
