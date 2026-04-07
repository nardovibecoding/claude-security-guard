#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""PostToolUse hook: auto pip install on VPS after requirements.txt edit.
Includes .pth supply-chain attack scan after install."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hook_base import run_hook, ssh_cmd
from vps_config import VPS_REPO


def check(tool_name, tool_input, input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    file_path = tool_input.get("file_path", "")
    return file_path.endswith("requirements.txt")


def scan_pth_files():
    """Scan venv for suspicious .pth files after pip install."""
    scan_script = f"""
cd {VPS_REPO} && source venv/bin/activate
python3 -c "
import glob, os, site
dirs = site.getsitepackages() + [site.getusersitepackages()]
suspicious = []
for d in dirs:
    if not os.path.isdir(d):
        continue
    for f in glob.glob(os.path.join(d, '*.pth')):
        name = os.path.basename(f)
        if name == 'distutils-precedence.pth':
            continue
        try:
            content = open(f).read()
            patterns = ['import ', 'exec(', 'eval(', 'base64', 'subprocess', 'os.system', '__import__']
            hits = [p for p in patterns if p in content]
            if hits:
                suspicious.append(f'ALERT: {{f}} contains: {{hits}}')
            elif name not in ('easy-install.pth',):
                suspicious.append(f'NEW: {{f}}')
        except Exception as e:
            suspicious.append(f'UNREADABLE: {{f}} ({{e}})')
if suspicious:
    for s in suspicious:
        print(s)
else:
    print('CLEAN')
"
"""
    ok, out = ssh_cmd(scan_script, timeout=15)
    return ok, out.strip()


def action(tool_name, tool_input, input_data):
    ok, out = ssh_cmd(
        f"cd {VPS_REPO} && source venv/bin/activate && pip install -r requirements.txt -q",
        timeout=30
    )
    if not ok:
        return f"VPS pip install FAILED: {out[:200]}"

    scan_ok, scan_out = scan_pth_files()
    if not scan_ok:
        return f"VPS: pip install OK. ⚠️ .pth scan failed: {scan_out[:200]}"
    if scan_out == "CLEAN":
        return "VPS: pip install OK. .pth scan clean ✅"
    else:
        return f"VPS: pip install OK. 🚨 .pth SUPPLY CHAIN ALERT:\n{scan_out}"


if __name__ == "__main__":
    run_hook(check, action, "auto_pip_install")
