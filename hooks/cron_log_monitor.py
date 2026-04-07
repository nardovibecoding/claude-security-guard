#!/usr/bin/env python3
"""SessionStart hook: check VPS cron job logs for recent errors."""
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
    # Grep recent errors from all cron job logs
    ok, out = ssh_cmd(
        "grep -l 'ERROR\\|CRITICAL\\|Traceback\\|FAILED' /tmp/*.log 2>/dev/null | head -10"
    )

    if not ok or not out:
        print("{}")
        return

    error_files = out.strip().splitlines()

    # Get last error line from each file
    details = []
    for log_file in error_files[:5]:
        ok2, last_err = ssh_cmd(
            f"grep -E 'ERROR|CRITICAL|Traceback|FAILED' {log_file} | tail -1"
        )
        if ok2 and last_err:
            name = log_file.split("/")[-1]
            details.append(f"  - `{name}`: {last_err[:120]}")

    if details:
        msg = f"**VPS log errors found in {len(error_files)} file(s):**\n"
        msg += "\n".join(details)
        print(json.dumps({"systemMessage": msg}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
