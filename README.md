# claude-security-guard

```bash
claude plugins install nardovibecoding/claude-security-guard
```

---

<div align="center">

**The most complete enforcement + security layer for Claude Code — hooks that block, tools that know, skills that audit.**

[![hooks](https://img.shields.io/badge/hooks-14-orange?style=for-the-badge)](hooks/)
[![mcp-tools](https://img.shields.io/badge/mcp--tools-28-blue?style=for-the-badge)](mcp/)
[![commands](https://img.shields.io/badge/commands-2-green?style=for-the-badge)](commands/)
[![license](https://img.shields.io/badge/license-AGPL--3.0-red?style=for-the-badge)](LICENSE)
[![platform](https://img.shields.io/badge/platform-macOS-lightgrey?style=for-the-badge)](#)

</div>

---

## Security

claude-security-guard runs a multilayer defense stack directly inside Claude Code:

- **Prompt injection detection** — 30+ patterns across English, Chinese, and Japanese
- **SSRF protection** — blocks private IP ranges, suspicious TLDs, and homograph attacks
- **Secret leak scanning** — finds API keys, tokens, passwords, and private keys before they leave your machine
- **File upload safety** — MIME mismatch detection, double-extension attacks, ClamAV integration
- **Dependency auditing** — typosquatting detection against known malicious package names
- **Exfiltration detection** — flags POST requests to unknown domains and file-to-HTTP patterns
Every security check runs as a hook (zero tokens) or an MCP tool call (one tool call). No instructions burned in context.

---

## Architecture

```
User / Claude Code
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  HOOKS — the muscle                                  │
│  Fires on every tool event. Silent. Zero tokens.     │
│  Blocks bad ops before they execute.                 │
│  Triggers side-effects (sync, restart, remind).      │
│  14 hooks across PreToolUse / PostToolUse / Stop     │
└──────────────────────┬───────────────────────────────┘
                       │ needs live state
                       ▼
┌──────────────────────────────────────────────────────┐
│  MCP SERVER — the brain                              │
│  Persistent process. Real answers.                   │
│  SSH to VPS. Diff configs. Count agents.             │
│  28 tools across 7 categories.                       │
└──────────────────────┬───────────────────────────────┘
                       │ needs multi-step orchestration
                       ▼
┌──────────────────────────────────────────────────────┐
│  SKILL COMMANDS — the personality                    │
│  User-invoked. Interactive.                          │
│  Orchestrates hooks + MCP + Claude reasoning.        │
│  2 commands: /system-check, /md-cleanup              │
└──────────────────────────────────────────────────────┘
```

**Rule of thumb:** if it should happen without being asked → hook. If Claude needs a real answer → MCP tool. If the user wants to run a workflow → skill command.

---

## Hooks (14)

Hooks fire automatically on tool events. Zero tokens consumed.

### Enforcement

| Hook | Event | What it does |
|------|-------|-------------|
| `guard_safety` | PreToolUse (Bash) | Blocks `rm -rf`, force push, hard reset, unauthorized VPS kills. Also: hook self-protection (blocks editing `~/.claude/hooks/`), credential dir read guard (`~/.ssh/`, `~/.aws/`), compound bash decomposition, `--no-verify` detection |
| `auto_scan_output` | PostToolUse (Read/Bash/WebFetch) | Scans tool output for prompt injection patterns before it reaches Claude's context |
| `canary_guard` | PreToolUse | Trip-wire detection — blocks any access to `SECURITY_CANARY` files |

### Ops Automation

| Hook | Event | What it does |
|------|-------|-------------|
| `auto_vps_sync` | PostToolUse (Bash) | Auto-pulls latest on VPS after every `git push` |
| `auto_dependency_grep` | PostToolUse (Bash) | Greps all references after a file move or delete |
| `auto_pip_install` | PostToolUse (Edit/Write) | Auto-installs on VPS after `requirements.txt` edit |
| `auto_bot_restart` | PostToolUse (Edit/Write) | Restarts bot process on VPS after persona config edit |
| `auto_restart_process` | PostToolUse (Edit/Write) | Restarts any tracked process after editing its source file |

### GitHub

| Hook | Event | What it does |
|------|-------|-------------|
| `auto_license` | PostToolUse (Bash) | After `gh repo create` → sets license, description, topics |
| `auto_repo_check` | PostToolUse (Bash) | After push to public repo → prompts README/description sync |

### Session & Memory

| Hook | Event | What it does |
|------|-------|-------------|
| `auto_skill_sync` | PostToolUse (Edit/Write) | Reminds to sync skills after `SKILL.md` edit |
| `auto_memory_index` | PostToolUse (Edit/Write) | Checks if new memory file is indexed in `MEMORY.md` |
| `auto_context_checkpoint` | UserPromptSubmit | Auto-triggers checkpoint at 20% context intervals |
| `auto_content_remind` | Stop | Before session ends → prompts to save tweet-worthy moments |

---

## MCP Tools (28)

Claude calls these directly. Live answers, no hallucinating from memory.

### Enforcement

| Tool | What it does |
|------|-------------|
| `agent_count` | How many background agents are running — check before spawning |
| `dependency_scan` | Grep references to any file or function across codebase + memory |
| `post_task_check` | Check session actions against known improvement patterns |
| `audit_query` | Query the persistent JSONL audit log by date, action type, or hook name |

### Ops

| Tool | What it does |
|------|-------------|
| `vps_status` | VPS reachability, bot processes, last git commit, uptime |
| `config_diff` | Compare local `.env` vs VPS `.env` — find mismatched keys |
| `sync_status` | Full sync state: GitHub ↔ Mac ↔ VPS ↔ templates in one call |
| `set_reminder` | Set a timed alert in the terminal (`16:55`, `30m`, `2h`) |

### Security

| Tool | What it does |
|------|-------------|
| `content_sanitize` | Scan text for 30+ prompt injection patterns (EN/CN/JP) |
| `url_check` | SSRF protection — block private IPs, suspicious TLDs, homograph attacks |
| `file_scan` | MIME mismatch, double extensions, suspicious code patterns, ClamAV |
| `dependency_audit` | Typosquatting detection, known malicious package database |
| `secret_leak_scan` | Scan files/dirs for API keys, tokens, passwords, private keys |
| `exfil_detect` | Detect data exfiltration — POST to unknown domains, file→HTTP patterns |
| `image_metadata` | Image type verification, embedded scripts, GPS data, EXIF analysis |

### Content

| Tool | What it does |
|------|-------------|
| `content_capture` | Save a tweet-worthy moment to the running draft log |
| `content_queue` | Manage tweet draft queue — add, list, pop next |

### Session

| Tool | What it does |
|------|-------------|
| `session_log` | Log an action or query the session log |
| `session_checkpoint` | Save session state at 20%/40%/60% context or before `/clear` |
| `session_transfer` | Transfer Claude Code session Mac → phone via Telegram |
| `session_id` | Return current session ID for resuming elsewhere |
| `context_budget` | Live token count across all MD-based context sources |

### GitHub

| Tool | What it does |
|------|-------------|
| `repo_sync_check` | Compare local skills/hooks vs GitHub repo — find drift |
| `github_readme_sync` | Generate updated README tables from local inventory |
| `github_metadata` | Get or set GitHub repo description and topics |
| `github_changelog` | Extract git log into structured changelog by category |

### Voice

| Tool | What it does |
|------|-------------|
| `voice_control` | Lock/unlock voice, mute/unmute TTS, check voice system status |
| `indicator_switch` | Switch voice indicator between menubar and floating dot |

---

## Skill Commands (2)

User-invoked slash commands for interactive audits.

| Command | What it does |
|---------|-------------|
| `/system-check` | Full health check — Mac + VPS processes, MCP servers, cron jobs, disk, memory, cookies. Clean status table. |
| `/md-cleanup` | 5-phase context budget auditor — CLAUDE.md, hookify rules, memory, skills. Token savings report + exec on approval. |

---

## Install

```bash
claude plugins install nardovibecoding/claude-security-guard
```

One command. Registers all hooks, starts the MCP server, activates skill commands.

---

## Configuration

Create a `.env` file in the plugin root:

```env
VPS_HOST=your.vps.hostname
VPS_USER=your_ssh_user
TELEGRAM_BOT_TOKEN_ADMIN=...   # optional — for session_transfer
ADMIN_USER_ID=...              # optional — for session_transfer
```

The MCP server reads this on startup via `mcp/vps.py`.

---

## Layer Comparison

| | Hooks | MCP Tools | Skill Commands |
|---|---|---|---|
| **Triggered by** | Automatic (tool events) | Claude (explicit call) | User (`/command`) |
| **Token cost** | Zero | ~1 tool call | Conversational |
| **Can block** | Yes | No | No |
| **Has state** | No | Yes | Via MCP |
| **SSH / network** | Yes (PostToolUse) | Yes | Via MCP |
| **Best for** | Enforcement, auto side-effects | Live queries, comparisons | Interactive audits, workflows |

---

## Why It Exists

It started with 41 rules sitting in Markdown files — pattern-matched, injected into every session, burning tokens before a single word of real work happened. Claude was reading the same rules hundreds of times a day.

Hooks replaced the rules. They run silently, pass or block, and cost nothing in context. But hooks are stateless — they can't check whether 3 agents are already running, SSH to a server, or compare two config files.

That's where the MCP server came in: persistent state, tool calls, real answers instead of instructions Claude has to remember.

The security layer came last — prompt injection, SSRF, secret scanning, and exfiltration detection running at the hook and tool layer, not burned into a system prompt.

The result got packaged as a plugin. One install. Everything active.

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=nardovibecoding/claude-security-guard&type=Date)](https://star-history.com/#nardovibecoding/claude-security-guard&Date)

---

## License

AGPL-3.0 — see [LICENSE](LICENSE).

Built by [nardovibecoding](https://github.com/nardovibecoding). Live system, not a demo.
