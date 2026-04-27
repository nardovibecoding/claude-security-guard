# simply-ops-guard

```bash
claude plugins install nardovibecoding/simply-ops-guard
```

---

<div align="center">

**49 hooks + 28 MCP tools — security enforcement, opsec scanning, and ops automation for Claude Code.**

[![hooks](https://img.shields.io/badge/hooks-49-orange?style=for-the-badge)](hooks/)
[![mcp-tools](https://img.shields.io/badge/mcp--tools-28-blue?style=for-the-badge)](mcp/)
[![license](https://img.shields.io/badge/license-AGPL--3.0-red?style=for-the-badge)](LICENSE)
[![platform](https://img.shields.io/badge/platform-macOS%20%2B%20Linux-lightgrey?style=for-the-badge)](#)

</div>

Claude Code does exactly what you tell it — including force-push to main, commit your `.env`, or run `rm -rf` on a production directory. There's no enforcement layer by default. This adds one.

---

## Architecture

```
PreToolUse hooks    → block dangerous ops before they run
PostToolUse hooks   → detect security issues + trigger ops automation
MCP server          → persistent state: agent count, VPS status, config diff
```

---

## Security Hooks (17)

| Hook | Event | What it does |
|------|-------|-------------|
| `guard_safety.py` | PreToolUse: Bash/Edit/Write/Read | Blocks destructive commands, rm -rf, credential reads, force-push, branch tampering |
| `canary_guard.py` | PreToolUse: Bash/Edit/Write/Read | Security canary — detects injection attempts in tool inputs |
| `auto_scan_output.py` | PostToolUse: Bash/Read/WebFetch | Scans tool output for leaked secrets, tokens, private data |
| `tg_security_guard.py` | PostToolUse: Edit/Write | Telegram-specific: prevents leaking chat IDs, tokens, user data |
| `tg_api_guard.py` | PostToolUse: Edit/Write | Blocks direct Telegram API calls that bypass the bot abstraction |
| `tg_qr_document.py` | PreToolUse: Edit/Write | Enforces QR codes sent as document not photo |
| `admin_only_guard.py` | PostToolUse: Edit/Write | Catches missing @admin_only decorators on sensitive handlers |
| `reasoning_leak_canary.py` | PostToolUse: Edit/Write | Detects when internal reasoning leaks into output or outreach files |
| `file_lock.py` | PreToolUse: Bash/Edit/Write/Read | Prevents two agents editing the same file simultaneously |
| `file_unlock.py` | PostToolUse: Edit/Write | Releases file lock after edit completes |
| `api_key_lookup.py` | PreToolUse: Bash | Forces checking reference doc before searching for API keys |
| `auto_pre_publish.py` | PreToolUse: Bash | Blocks `gh repo visibility public` until all checks pass |
| `reddit_api_block.py` | PostToolUse: Edit/Write | Blocks Reddit OAuth API usage — use scraping instead |
| `skill_disable_not_delete.py` | PreToolUse: Bash | Enforces renaming SKILL.md to .disabled instead of deleting |
| `agent_cascade_guard.py` | PreToolUse: Agent | Prevents agents spawning sub-agents (cascade protection) |
| `agent_count_guard.py` | PreToolUse: Agent | Blocks >1 agent per turn, requires user approval for more |
| `agent_simplicity_guard.py` | PreToolUse: Agent | Defaults agents to Haiku unless task complexity justifies Sonnet |
| `temp_file_guard.py` | PostToolUse: Edit/Write | Warns when code writes to /tmp without proper cleanup |

---

## Ops Automation Hooks (20)

| Hook | Event | What it does |
|------|-------|-------------|
| `auto_vps_sync.py` | PostToolUse: Bash | git push → VPS auto-pulls |
| `auto_pip_install.py` | PostToolUse: Edit/Write | requirements.txt edit → auto pip install on VPS |
| `auto_bot_restart.py` | PostToolUse: Edit/Write | Persona JSON edit → restart bot on VPS |
| `auto_restart_process.py` | PostToolUse: Edit/Write | Source file edit → restart its process |
| `auto_skill_sync.py` | PostToolUse: Edit/Write | SKILL.md edit → sync skills directory |
| `auto_hook_deploy.py` | PostToolUse: Edit/Write | Hook file edit → auto-deploy to hooks dir |
| `mcp_server_restart.py` | PostToolUse: Edit/Write | MCP server source edit → restart it on VPS |
| `auto_memory_index.py` | PostToolUse: Write | New memory file → verify it's in MEMORY.md index |
| `verify_infra.py` | PostToolUse: Bash | crontab/systemctl setup → auto-verify on target |
| `auto_context_checkpoint.py` | UserPromptSubmit | Every 20% context → auto checkpoint |
| `auto_content_remind.py` | Stop | Session end → remind to save tweet-worthy moments |
| `memory_auto_commit.py` | Stop | Session end → auto-commit changed memory files |
| `cookie_health.py` | SessionStart | Session start → check MCP health + cookie freshness on VPS |
| `cron_log_monitor.py` | SessionStart | Session start → check VPS cron logs for recent errors |
| `agent_tracker.py` | PreToolUse+SubagentStop | Logs agent spawns and completion status across /clear boundaries |
| `auto_context_exit.py` | Stop | Exits session cleanly when exit_pending marker is set |
| `context_50_check.py` | UserPromptSubmit | Injects /s reminder when context hits 50% |
| `dispatcher_pre.py` | PreToolUse | Single dispatcher routing to all PreToolUse hooks (replaces ~15 spawns) |
| `dispatcher_post.py` | PostToolUse | Single dispatcher routing to all PostToolUse hooks (replaces ~25 spawns) |
| `pre_compact_save.py` | PreCompact | Saves transcript + reminds to /s before compaction |

---

## MCP Server (28 tools)

Persistent process — holds state, connects to VPS, answers real-time queries.

| Category | Tools |
|----------|-------|
| Security scanning | `content_sanitize`, `url_check`, `file_scan`, `secret_leak_scan`, `exfil_detect`, `image_metadata`, `dependency_audit` |
| VPS ops | `vps_status`, `config_diff`, `repo_sync_check`, `github_readme_sync`, `github_metadata`, `github_changelog` |
| Session | `agent_count`, `context_budget`, `session_log`, `session_checkpoint`, `session_transfer`, `session_id`, `post_task_check` |
| Content | `content_capture`, `content_queue` |
| Tools | `set_reminder`, `indicator_switch` |

---

## Install

```bash
claude plugins install nardovibecoding/simply-ops-guard
```

Requires Python 3.10+ and optional VPS config for ops automation hooks.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/nardovibecoding/simply-ops-guard/main/install.sh)
```

---

## Related

- [simply-quality-gate](https://github.com/nardovibecoding/simply-quality-gate) — 10 hooks for code quality enforcement

---

## License

AGPL-3.0 — Copyright (c) 2026 Nardo (nardovibecoding)
