#!/usr/bin/env bash
# Claude Security Guard — one-liner installer
# curl -fsSL https://raw.githubusercontent.com/nardovibecoding/claude-security-guard/main/install.sh | bash
set -euo pipefail

INSTALL_DIR="$HOME/claude-security-guard"
SETTINGS="$HOME/.claude/settings.json"

RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' CYAN='\033[0;36m' BOLD='\033[1m' NC='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}"
echo "  ╔═════════════════════════════════════════╗"
echo "  ║   Claude Security Guard Installer        ║"
echo "  ║   14 hooks + 28 MCP tools + 2 commands   ║"
echo "  ╚═════════════════════════════════════════╝"
echo -e "${NC}"

# --- Check Python ---
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗ Python 3 is required. Install it first.${NC}"
  exit 1
fi

# --- Clone or update ---
if [ -d "$INSTALL_DIR/.git" ]; then
  echo -e "${YELLOW}→ Updating existing install...${NC}"
  git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || true
else
  if [ -d "$INSTALL_DIR" ]; then
    echo -e "${RED}✗ $INSTALL_DIR exists but is not a git repo. Remove it first.${NC}"
    exit 1
  fi
  echo -e "${GREEN}→ Cloning repository...${NC}"
  git clone https://github.com/nardovibecoding/claude-security-guard.git "$INSTALL_DIR"
fi

# --- Install MCP dependencies ---
echo -e "${GREEN}→ Installing MCP server dependencies...${NC}"
pip3 install --quiet mcp 2>/dev/null || pip install --quiet mcp 2>/dev/null || echo -e "${YELLOW}  Warning: couldn't install mcp package. Install manually: pip install mcp${NC}"

# --- Optional VPS config ---
echo ""
echo -e "${BOLD}Optional: VPS configuration${NC}"
read -rp "VPS hostname (leave blank to skip): " VPS_HOST
if [ -n "$VPS_HOST" ]; then
  read -rp "VPS user [root]: " VPS_USER
  VPS_USER=${VPS_USER:-root}
  cat > "$INSTALL_DIR/.env" << ENVEOF
VPS_HOST=$VPS_HOST
VPS_USER=$VPS_USER
ENVEOF
  echo -e "  ${GREEN}Saved .env${NC}"
fi

# --- Patch settings.json ---
echo -e "${GREEN}→ Configuring hooks + MCP server...${NC}"
mkdir -p "$HOME/.claude"

python3 << 'PYEOF'
import json, os

INSTALL_DIR = os.path.expanduser("~/claude-security-guard")
SETTINGS = os.path.expanduser("~/.claude/settings.json")

if os.path.exists(SETTINGS):
    with open(SETTINGS) as f:
        settings = json.load(f)
else:
    settings = {}

hooks = settings.setdefault("hooks", {})
MARKER = "claude-security-guard"

HOOK_DEFS = {
    "PreToolUse": [
        {"matcher": "Bash|Write|Edit|Read", "hooks": [
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/guard_safety.py", "timeout": 5000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/canary_guard.py", "timeout": 3000},
        ]},
    ],
    "PostToolUse": [
        {"matcher": "Bash|Read|WebFetch", "hooks": [
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_scan_output.py", "timeout": 3000},
        ]},
        {"matcher": "Bash", "hooks": [
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_vps_sync.py", "timeout": 15000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_dependency_grep.py", "timeout": 10000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_license.py", "timeout": 15000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_repo_check.py", "timeout": 5000},
        ]},
        {"matcher": "Edit|Write", "hooks": [
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_pip_install.py", "timeout": 30000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_bot_restart.py", "timeout": 15000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_skill_sync.py", "timeout": 5000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_restart_process.py", "timeout": 15000},
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_memory_index.py", "timeout": 5000},
        ]},
    ],
    "UserPromptSubmit": [
        {"matcher": "", "hooks": [
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_context_checkpoint.py", "timeout": 3000},
        ]},
    ],
    "Stop": [
        {"matcher": "", "hooks": [
            {"type": "command", "command": f"python3 {INSTALL_DIR}/hooks/auto_content_remind.py", "timeout": 3000},
        ]},
    ],
}

for event, entries in HOOK_DEFS.items():
    event_hooks = hooks.setdefault(event, [])
    event_hooks[:] = [h for h in event_hooks if not any(MARKER in hook.get("command", "") for hook in h.get("hooks", []))]
    event_hooks.extend(entries)

# Add MCP server
mcp = settings.setdefault("mcpServers", {})
mcp["security-guard"] = {
    "command": "python3",
    "args": [f"{INSTALL_DIR}/mcp/server.py"]
}

with open(SETTINGS, "w") as f:
    json.dump(settings, f, indent=2)

print("  Hooks + MCP server configured in ~/.claude/settings.json")
PYEOF

# --- Done ---
echo ""
echo -e "${GREEN}${BOLD}✓ Claude Security Guard installed!${NC}"
echo ""
echo -e "  ${BOLD}14 hooks${NC} block dangerous commands, auto-sync, scan output."
echo -e "  ${BOLD}28 MCP tools${NC} for VPS management, file locking, sanitization."
echo -e "  ${BOLD}2 commands${NC}: /system-check, /md-cleanup"
echo ""
echo -e "  ${YELLOW}Restart Claude Code if it's already running.${NC}"
echo ""
