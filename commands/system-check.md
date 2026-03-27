---
name: system-check
description: Full system health check — Mac + VPS processes, MCP servers, cron jobs, disk, memory, cookies, heartbeat. One command to see everything.
---

Run a comprehensive system health check across Mac and VPS.

## Check these in parallel:

### VPS (ssh bernard@157.180.28.14):
1. **Bot processes**: `pgrep -fa "run_bot|admin_bot"` — daliu, sbf, admin alive?
2. **systemd services**: `systemctl is-active telegram-bots xhs-mcp douyin-mcp` — all active?
3. **MCP health**: `curl -s localhost:18060/health && curl -s localhost:18070/health`
4. **Heartbeat**: `cat .admin_heartbeat` — age < 60s?
5. **Disk**: `df -h /` — usage %
6. **Memory**: `free -m` — usage
7. **Docker**: `docker ps` — RSSHub running?
8. **Cookie age**: `stat -c %Y twitter_cookies.json` — how old?
9. **Today's cron jobs**: check which daily jobs ran (grep today's date in each log)
10. **Recent errors**: `grep -i "error\|traceback" /tmp/start_all.log | tail -5`

### Mac:
1. **Voice daemon**: `pgrep -f voice_daemon`
2. **Recording indicator**: `pgrep -f recording_indicator`
3. **Sync script**: check `/tmp/claude-memory-sync.log` last run time
4. **ComfyUI**: `curl -s localhost:8188/system_stats`

## Output format:
Present as a clean status table with ✅/❌ for each item.
