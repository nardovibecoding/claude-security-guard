#!/usr/bin/env python3
"""PostToolUse hook: restart MCP servers on VPS after editing their source files."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook, ssh_cmd

# Map: path pattern → systemd service name
MCP_SERVICES = {
}


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return any(pattern in file_path for pattern in MCP_SERVICES)


def action(tool_name, tool_input, input_data):
    file_path = tool_input.get("file_path", "")
    for pattern, service in MCP_SERVICES.items():
        if pattern in file_path:
            ok, out = ssh_cmd(f"systemctl --user restart {service} 2>&1")
            if ok:
                # Verify it's actually running
                ok2, status = ssh_cmd(f"systemctl --user is-active {service} 2>&1")
                if ok2 and "active" in status:
                    return f"✅ Restarted `{service}` on VPS after file edit."
                return f"⚠️ Restarted `{service}` but status: {status}"
            return f"⚠️ Failed to restart `{service}`: {out}"
    return None


if __name__ == "__main__":
    run_hook(check, action, "mcp_server_restart")
