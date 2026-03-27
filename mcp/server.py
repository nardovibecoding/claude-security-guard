#!/usr/bin/env python3
"""ops-guard MCP server — stateful queries for Claude Code enforcement."""

import os
import re
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from vps import ssh_cmd, load_env
from patterns import check_patterns
import lib as _lib

mcp = FastMCP("ops-guard")

# Share session state with lib
_session_actions = _lib.session_actions


# --- Tool 1: agent_count ---
@mcp.tool()
def agent_count() -> dict:
    """Check how many background agents are currently running. Call before spawning a new agent."""
    running = 0
    tmp_dirs = list(Path("/tmp").glob("claude-*/"))
    for tmp_dir in tmp_dirs:
        tasks_dir = tmp_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for output_file in tasks_dir.glob("*.output"):
            # Check if file is still being written to (modified in last 120s)
            try:
                mtime = output_file.stat().st_mtime
                if time.time() - mtime < 120:
                    running += 1
            except OSError:
                continue

    return {
        "running": running,
        "max": 3,
        "can_spawn": running < 3
    }


# --- Tool 2: vps_status ---
@mcp.tool()
def vps_status() -> dict:
    """Check VPS health: reachability, running bots, last git commit, uptime."""
    env = load_env()
    vps_ssh = f"{env['VPS_USER']}@{env['VPS_HOST']}"

    # Ping
    ok, _ = ssh_cmd(vps_ssh, "echo ok", timeout=5)
    if not ok:
        return {"reachable": False, "error": "SSH connection failed"}

    # Bot processes
    _, procs = ssh_cmd(vps_ssh, "pgrep -a -f 'run_bot.py|admin_bot' 2>/dev/null || echo 'none'")
    bots = []
    for line in procs.splitlines():
        m = re.search(r"run_bot\.py (\w+)", line)
        if m:
            bots.append(m.group(1))
        if "admin_bot" in line:
            bots.append("admin")

    # Last commit
    _, commit = ssh_cmd(vps_ssh, "cd ~/telegram-claude-bot && git log --oneline -1 2>/dev/null")

    # Uptime
    _, uptime = ssh_cmd(vps_ssh, "uptime -p 2>/dev/null || uptime")

    return {
        "reachable": True,
        "bots_running": bots,
        "last_commit": commit.strip(),
        "uptime": uptime.strip()
    }


# --- Tool 3: config_diff ---
@mcp.tool()
def config_diff() -> dict:
    """Compare Mac .env vs VPS .env — find keys present on one but not the other."""
    env = load_env()
    vps_ssh = f"{env['VPS_USER']}@{env['VPS_HOST']}"

    mac_env_path = Path.home() / "telegram-claude-bot" / ".env"
    mac_keys = set()
    if mac_env_path.exists():
        for line in mac_env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                mac_keys.add(line.split("=", 1)[0].strip())

    ok, vps_env_text = ssh_cmd(vps_ssh, "cat ~/telegram-claude-bot/.env 2>/dev/null")
    vps_keys = set()
    if ok:
        for line in vps_env_text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                vps_keys.add(line.split("=", 1)[0].strip())

    mac_only = sorted(mac_keys - vps_keys)
    vps_only = sorted(vps_keys - mac_keys)

    mismatches = []
    for k in mac_only:
        mismatches.append({"key": k, "mac": "set", "vps": "missing"})
    for k in vps_only:
        mismatches.append({"key": k, "mac": "missing", "vps": "set"})

    return {
        "mac_keys": len(mac_keys),
        "vps_keys": len(vps_keys),
        "mismatches": mismatches,
        "in_sync": len(mismatches) == 0
    }


# --- Tool 4: dependency_scan ---
@mcp.tool()
def dependency_scan(target: str) -> dict:
    """Grep all references to a file or function across codebase, memory, and skills.

    Args:
        target: filename, function name, or pattern to search for
    """
    search_dirs = [
        str(Path.home() / "telegram-claude-bot"),
        str(Path.home() / ".claude"),
    ]
    refs = []
    for search_dir in search_dirs:
        try:
            result = subprocess.run(
                ["grep", "-rn", target, search_dir,
                 "--include=*.py", "--include=*.md", "--include=*.json",
                 "--include=*.sh", "--include=*.yaml"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().splitlines()[:30]:
                refs.append(line)
        except (subprocess.TimeoutExpired, Exception):
            continue

    return {
        "target": target,
        "references": refs[:30],
        "count": len(refs)
    }


# --- Tool 5: context_budget ---
@mcp.tool()
def context_budget() -> dict:
    """Live token count across all MD-based context sources."""
    results = {}

    # CLAUDE.md
    claude_md = Path.home() / "telegram-claude-bot" / "CLAUDE.md"
    if claude_md.exists():
        lines = len(claude_md.read_text().splitlines())
        results["claude_md"] = {"lines": lines, "est_tokens": int(lines * 2.5)}

    # Hookify rules
    hookify_files = list(Path.home().joinpath(".claude").glob("hookify.*.local.md"))
    if hookify_files:
        total_chars = sum(f.read_text().__len__() for f in hookify_files)
        results["hookify_rules"] = {"files": len(hookify_files), "chars": total_chars, "est_tokens": int(total_chars / 3.5)}
    else:
        results["hookify_rules"] = {"files": 0, "chars": 0, "est_tokens": 0}

    # MEMORY.md
    memory_md = Path.home() / ".claude/projects/-Users-bernard/memory/MEMORY.md"
    if memory_md.exists():
        lines = len(memory_md.read_text().splitlines())
        results["memory_index"] = {"lines": lines, "est_tokens": int(lines * 8)}

    # Skills YAML
    total_yaml_chars = 0
    skill_count = 0
    for skill_md in Path.home().joinpath(".claude/skills").rglob("SKILL.md"):
        content = skill_md.read_text()
        # Extract YAML frontmatter only
        parts = content.split("---", 2)
        if len(parts) >= 3:
            total_yaml_chars += len(parts[1])
            skill_count += 1
    results["skills_yaml"] = {"skills": skill_count, "chars": total_yaml_chars, "est_tokens": int(total_yaml_chars / 3.5)}

    # Total
    total = sum(v.get("est_tokens", 0) for v in results.values())
    results["total_est_tokens"] = total

    return results


# --- Tool 6: post_task_check ---
@mcp.tool()
def post_task_check() -> dict:
    """Check recent session actions against known improvement patterns. Call after completing a task."""
    actions = list(_session_actions)
    suggestions = check_patterns(actions)

    # Check if session produced content-worthy material
    content_worthy = False
    content_signals = []
    for a in actions:
        detail = a.get("detail", "")
        act = a.get("action", "")
        if act in ("new_hook", "new_mcp_tool", "new_skill", "architecture_change"):
            content_worthy = True
            content_signals.append(f"{act}: {detail}")
        if act == "file_edit" and any(k in detail for k in ["CLAUDE.md", "settings.json", "hookify"]):
            content_worthy = True
            content_signals.append(f"config change: {detail}")

    if content_worthy:
        suggestions.append(f"Content-worthy session! Signals: {', '.join(content_signals[:5])}. Use content_capture to save moments.")

    return {
        "recent_actions": actions[-10:],
        "suggestions": suggestions,
        "content_worthy": content_worthy
    }


# --- Tool 7: session_log (delegates to lib) ---
@mcp.tool()
def session_log(action: str = "", detail: str = "", query: bool = False) -> dict:
    """Log a session action or query the log.

    Args:
        action: action type (e.g. "git_push", "file_edit", "agent_spawn")
        detail: additional detail (e.g. file path, branch name)
        query: if True, return the log instead of appending
    """
    return _lib.session_log(action, detail, query)


# --- Tool 8: content_capture (delegates to lib) ---
@mcp.tool()
def content_capture(moment: str, category: str = "insight") -> dict:
    """Save a content-worthy moment to the running draft log. Call when something interesting happens worth tweeting about.

    Args:
        moment: what happened — the insight, discovery, result, or aha moment
        category: one of: insight, result, code, number, journey, mistake
    """
    return _lib.content_capture(moment, category)


# --- Tool 9: repo_sync_check ---
@mcp.tool()
def repo_sync_check(repo: str = "claude-curated") -> dict:
    """Compare local skills/hooks vs GitHub repo — find what's out of sync.

    Args:
        repo: GitHub repo name under nardovibecoding (default: claude-curated)
    """
    import tempfile

    results = {"repo": f"nardovibecoding/{repo}", "diffs": []}

    # Clone to temp dir (shallow)
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_result = subprocess.run(
            ["git", "clone", "--depth=1", f"https://github.com/nardovibecoding/{repo}.git", tmpdir],
            capture_output=True, text=True, timeout=30
        )
        if clone_result.returncode != 0:
            return {"error": f"Clone failed: {clone_result.stderr[:200]}"}

        github_dir = Path(tmpdir)

        # Compare local skills vs repo skills
        local_skills = Path.home() / ".claude" / "skills"
        repo_skills = github_dir / "skills"

        if repo_skills.exists():
            # Find SKILL.md files in repo
            for repo_skill in repo_skills.rglob("SKILL.md"):
                rel_path = repo_skill.relative_to(repo_skills)
                skill_name = rel_path.parent.name
                # Find matching local skill
                local_match = local_skills / skill_name / "SKILL.md"
                if local_match.exists():
                    local_content = local_match.read_text()
                    repo_content = repo_skill.read_text()
                    if local_content != repo_content:
                        results["diffs"].append({
                            "file": f"skills/{rel_path}",
                            "status": "modified_locally",
                            "local_lines": len(local_content.splitlines()),
                            "repo_lines": len(repo_content.splitlines())
                        })
                else:
                    results["diffs"].append({
                        "file": f"skills/{rel_path}",
                        "status": "repo_only"
                    })

            # Local skills not in repo
            for local_skill in local_skills.iterdir():
                if not local_skill.is_dir():
                    continue
                skill_md = local_skill / "SKILL.md"
                if not skill_md.exists():
                    continue
                # Check if this skill is anywhere in repo
                found = False
                for repo_skill in repo_skills.rglob("SKILL.md"):
                    if repo_skill.parent.name == local_skill.name:
                        found = True
                        break
                if not found:
                    results["diffs"].append({
                        "file": f"skills/{local_skill.name}/SKILL.md",
                        "status": "local_only"
                    })

        # Compare local hooks vs repo hooks
        local_hooks = Path.home() / ".claude" / "hooks"
        repo_hooks = github_dir / "hooks"
        if repo_hooks.exists() and local_hooks.exists():
            for repo_hook in repo_hooks.rglob("*.py"):
                rel = repo_hook.relative_to(repo_hooks)
                # Find matching local file
                for local_file in local_hooks.rglob(repo_hook.name):
                    if local_file.read_text() != repo_hook.read_text():
                        results["diffs"].append({
                            "file": f"hooks/{rel}",
                            "status": "modified_locally"
                        })
                    break
                else:
                    results["diffs"].append({
                        "file": f"hooks/{rel}",
                        "status": "repo_only"
                    })

    results["in_sync"] = len(results["diffs"]) == 0
    results["total_diffs"] = len(results["diffs"])
    return results


# --- Tool 10: github_readme_sync ---
@mcp.tool()
def github_readme_sync(repo: str = "claude-curated") -> dict:
    """Generate an updated README skills/hooks inventory from local state. Returns markdown that can replace the repo README tables.

    Args:
        repo: GitHub repo name (default: claude-curated)
    """
    local_skills = Path.home() / ".claude" / "skills"
    local_hooks = Path.home() / ".claude" / "hooks"

    # Inventory active skills
    skills = []
    for skill_dir in sorted(local_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        content = skill_md.read_text()
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        # Extract name and first line of description
        name = skill_dir.name
        desc = ""
        for line in parts[1].splitlines():
            if line.strip().startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip('"').strip("|").strip()
                if not desc:
                    # Multi-line description, get next line
                    idx = parts[1].splitlines().index(line)
                    remaining = parts[1].splitlines()[idx + 1:]
                    for dl in remaining:
                        dl = dl.strip()
                        if dl and not dl.startswith("Triggers:") and not dl.startswith("NOT FOR:"):
                            desc = dl
                            break
                break
        skills.append({"name": name, "description": desc[:100]})

    # Inventory hooks
    hooks = []
    for hook_file in sorted(local_hooks.glob("auto_*.py")):
        name = hook_file.stem.replace("auto_", "")
        # Read first docstring line
        content = hook_file.read_text()
        desc = ""
        for line in content.splitlines():
            if '"""' in line and "hook:" in line.lower():
                desc = line.split('"""')[1].strip() if '"""' in line else ""
                break
            if line.startswith('"""'):
                desc = line.strip('"""').strip()
                break
        hooks.append({"name": name, "description": desc[:100]})

    # Also count guard hooks
    for hook_file in sorted(local_hooks.glob("guard_*.py")):
        name = hook_file.stem.replace("guard_", "")
        content = hook_file.read_text()
        desc = ""
        for line in content.splitlines():
            if '"""' in line:
                desc = line.strip('"""').strip()
                break
        hooks.append({"name": f"guard-{name}", "description": desc[:100]})

    # Generate markdown tables
    skill_table = "| Skill | Description |\n|---|---|\n"
    for s in skills:
        skill_table += f"| {s['name']} | {s['description']} |\n"

    hook_table = "| Hook | Description |\n|---|---|\n"
    for h in hooks:
        hook_table += f"| {h['name']} | {h['description']} |\n"

    return {
        "repo": repo,
        "skills_count": len(skills),
        "hooks_count": len(hooks),
        "skills_table": skill_table,
        "hooks_table": hook_table,
        "badge_text": f"skills-{len(skills)}--hooks-{len(hooks)}"
    }


# --- Tool 11: content_queue (delegates to lib) ---
@mcp.tool()
def content_queue(action: str = "list", tweet: str = "", priority: str = "normal") -> dict:
    """Manage tweet draft queue. Add drafts, list queue, get next to post.

    Args:
        action: "add" to add a draft, "list" to see queue, "next" to get highest priority, "posted" to mark top as done
        tweet: tweet text (required for "add")
        priority: "high", "normal", "low" (for "add")
    """
    return _lib.content_queue(action, tweet, priority)


# --- Tool 12: github_metadata ---
@mcp.tool()
def github_metadata(repo: str, description: str = "", topics: list[str] = None, action: str = "get") -> dict:
    """Get or set GitHub repo metadata (description, topics).

    Args:
        repo: repo name under nardovibecoding (e.g. "claude-curated")
        description: new description (for action="set")
        topics: list of topics/tags (for action="set")
        action: "get" to read current, "set" to update
    """
    full_repo = f"nardovibecoding/{repo}"

    if action == "get":
        result = subprocess.run(
            ["gh", "repo", "view", full_repo, "--json", "description,repositoryTopics,url,stargazerCount"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return {"error": result.stderr[:200]}
        import json as _json
        return _json.loads(result.stdout)

    elif action == "set":
        results = {}
        if description:
            r = subprocess.run(
                ["gh", "repo", "edit", full_repo, "--description", description],
                capture_output=True, text=True, timeout=15
            )
            results["description"] = "updated" if r.returncode == 0 else r.stderr[:100]

        if topics:
            for topic in topics:
                r = subprocess.run(
                    ["gh", "repo", "edit", full_repo, "--add-topic", topic],
                    capture_output=True, text=True, timeout=10
                )
                results[f"topic_{topic}"] = "added" if r.returncode == 0 else r.stderr[:100]

        return results

    return {"error": f"unknown action: {action}"}


# --- Tool 13: github_changelog ---
@mcp.tool()
def github_changelog(repo_path: str = "", since: str = "", limit: int = 20) -> dict:
    """Extract git log into structured data for changelog generation.

    Args:
        repo_path: local path to repo (default: ~/telegram-claude-bot)
        since: git date filter (e.g. "2026-03-20", "1 week ago")
        limit: max commits to return
    """
    if not repo_path:
        repo_path = str(Path.home() / "telegram-claude-bot")

    cmd = ["git", "-C", repo_path, "log", f"--max-count={limit}",
           "--pretty=format:%H|%h|%an|%ad|%s", "--date=short"]
    if since:
        cmd.append(f"--since={since}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return {"error": result.stderr[:200]}

    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "date": parts[3],
                "message": parts[4]
            })

    # Categorize by conventional commit prefix
    categories = {"feat": [], "fix": [], "refactor": [], "docs": [], "other": []}
    for c in commits:
        msg = c["message"].lower()
        if msg.startswith("feat") or "add " in msg or "new " in msg:
            categories["feat"].append(c)
        elif msg.startswith("fix") or "fix " in msg or "bug" in msg:
            categories["fix"].append(c)
        elif msg.startswith("refactor") or "trim" in msg or "clean" in msg or "consolidat" in msg:
            categories["refactor"].append(c)
        elif msg.startswith("doc") or "readme" in msg:
            categories["docs"].append(c)
        else:
            categories["other"].append(c)

    return {
        "repo": repo_path,
        "total_commits": len(commits),
        "commits": commits,
        "categories": {k: len(v) for k, v in categories.items()},
        "summary": {k: [c["message"] for c in v] for k, v in categories.items() if v}
    }


# --- Tool 14: session_checkpoint (delegates to lib) ---
@mcp.tool()
def session_checkpoint(summary: str, key_decisions: list[str] = None, files_changed: list[str] = None) -> dict:
    """Save session state to checkpoint file. Call at context 20%/40%/60% or before /clear.

    Args:
        summary: what was accomplished this session (2-3 sentences)
        key_decisions: important decisions made (list of strings)
        files_changed: key files created or modified
    """
    return _lib.session_checkpoint(summary, key_decisions, files_changed)


# --- Tool 15: session_transfer ---
@mcp.tool()
def session_transfer(direction: str, summary: str = "", session_id: str = "") -> dict:
    """Transfer Claude Code session between Mac and phone via Telegram.

    Args:
        direction: "out" (Mac → phone) or "in" (phone → Mac)
        summary: session context summary (required for "out")
        session_id: session ID to transfer (required for "out")
    """
    env = load_env()
    vps_ssh = f"{env['VPS_USER']}@{env['VPS_HOST']}"

    if direction == "out":
        if not summary or not session_id:
            return {"error": "provide summary and session_id for transfer out"}

        # Write pending file to VPS
        ok, _ = ssh_cmd(vps_ssh,
            f"mkdir -p ~/.claude/projects/-home-bernard/memory && "
            f"echo '{session_id}' > ~/.claude/projects/-home-bernard/memory/pending_resume.txt",
            timeout=10
        )

        # Send TG notification
        import urllib.request
        import urllib.parse
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_ADMIN", "")
        admin_id = os.environ.get("ADMIN_USER_ID", "")
        if bot_token and admin_id:
            msg = f"🟧 <b>Mac → Phone</b>\n\n{summary}\n\nSession: <code>{session_id}</code>"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": admin_id,
                "text": msg,
                "parse_mode": "HTML"
            }).encode()
            try:
                urllib.request.urlopen(url, data, timeout=10)
            except Exception:
                pass

        return {"transferred": True, "direction": "out", "session_id": session_id}

    elif direction == "in":
        # Read pending session from VPS
        ok, pending = ssh_cmd(vps_ssh,
            "cat ~/.claude/projects/-home-bernard/memory/pending_resume.txt 2>/dev/null")
        if ok and pending.strip():
            return {"direction": "in", "session_id": pending.strip(), "ready": True}
        return {"direction": "in", "ready": False, "error": "no pending session"}

    return {"error": f"direction must be 'out' or 'in', got '{direction}'"}


# --- Tool 16: session_id ---
@mcp.tool()
def session_id() -> dict:
    """Return the current Claude Code session/chat ID for resuming elsewhere."""
    # Check for session ID in common locations
    import glob as _glob
    sessions = sorted(
        Path("/tmp").glob("claude-*/"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True
    )
    if sessions:
        latest = sessions[0].name
        return {"session_dir": str(sessions[0]), "hint": latest}
    return {"error": "no active session found in /tmp"}


# --- Tool 17: set_reminder ---
@mcp.tool()
def set_reminder(time_spec: str, message: str) -> dict:
    """Set a timer reminder that alerts in the terminal.

    Args:
        time_spec: "16:55" for absolute HKT time, or "30m"/"2h" for relative
        message: reminder text
    """
    import re as _re
    from datetime import datetime, timedelta
    import zoneinfo

    hkt = zoneinfo.ZoneInfo("Asia/Hong_Kong")
    now = datetime.now(hkt)

    # Parse time spec
    rel_match = _re.match(r"^(\d+)(m|h|min|hour)s?$", time_spec)
    abs_match = _re.match(r"^(\d{1,2}):(\d{2})$", time_spec)

    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2)
        if unit.startswith("h"):
            seconds = amount * 3600
        else:
            seconds = amount * 60
        target = now + timedelta(seconds=seconds)
    elif abs_match:
        hour, minute = int(abs_match.group(1)), int(abs_match.group(2))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        seconds = int((target - now).total_seconds())
    else:
        return {"error": f"can't parse time: {time_spec}. Use HH:MM or Nm/Nh"}

    # Launch background timer
    alert = f"⏰⏰⏰ 提醒：{message} ⏰⏰⏰"
    subprocess.Popen(
        ["bash", "-c", f"sleep {seconds} && echo -e '\\n\\n{alert}\\n'"],
        stdout=None, stderr=None
    )

    target_str = target.strftime("%H:%M HKT")
    return {"set": True, "target": target_str, "seconds": seconds, "message": message}


# --- Tool 18: indicator_switch (local only, not in public plugin) ---
@mcp.tool()
def indicator_switch(mode: str) -> dict:
    """Switch voice indicator between menubar (dual monitor) and floating dot (single monitor).

    Args:
        mode: "plugged" for menubar, "unplugged" for floating dot
    """
    subprocess.run(["pkill", "-f", "recording_indicator.py"], capture_output=True)
    time.sleep(0.5)

    if mode == "plugged":
        indicator_mode = "menubar"
    elif mode == "unplugged":
        indicator_mode = "dot"
    else:
        return {"error": f"mode must be 'plugged' or 'unplugged', got '{mode}'"}

    subprocess.Popen(
        ["python3", "/tmp/claude-voice-control/recording_indicator.py", "--mode", indicator_mode],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    return {"switched": True, "mode": indicator_mode}


# --- Tool 19: sync_status ---
@mcp.tool()
def sync_status() -> dict:
    """Check sync state across all systems: GitHub ↔ Mac ↔ VPS ↔ templates. One call to see everything."""
    from datetime import datetime
    env = load_env()
    vps_ssh = f"{env['VPS_USER']}@{env['VPS_HOST']}"
    result = {"checked_at": datetime.now().strftime("%Y-%m-%d %H:%M HKT")}

    # --- 1. GitHub ↔ Mac sync (per repo) ---
    repos = {
        "telegram-claude-bot": Path.home() / "telegram-claude-bot",
        "ops-guard-mcp": Path.home() / "ops-guard-mcp",
        "security-shield-mcp": Path.home() / "security-shield-mcp",
        "claude-curated": Path.home() / "claude-curated",
    }
    github_mac = {}
    for name, local_path in repos.items():
        info = {}
        if not local_path.exists():
            info["status"] = "no local clone"
            github_mac[name] = info
            continue
        subprocess.run(["git", "-C", str(local_path), "fetch", "--quiet"], capture_output=True, timeout=10)
        # Commits ahead/behind
        r = subprocess.run(
            ["git", "-C", str(local_path), "rev-list", "--left-right", "--count", "HEAD...origin/main"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split()
            ahead = int(parts[0]) if len(parts) > 0 else 0
            behind = int(parts[1]) if len(parts) > 1 else 0
            info["ahead"] = ahead
            info["behind"] = behind
            info["synced"] = ahead == 0 and behind == 0
        # Uncommitted
        r = subprocess.run(["git", "-C", str(local_path), "status", "--porcelain"], capture_output=True, text=True, timeout=5)
        info["uncommitted"] = len([l for l in r.stdout.strip().splitlines() if l.strip()])
        # HEAD
        r = subprocess.run(["git", "-C", str(local_path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        info["head"] = r.stdout.strip()
        github_mac[name] = info
    result["github_mac"] = github_mac

    # --- 2. Mac ↔ VPS sync ---
    vps = {}
    ok, _ = ssh_cmd(vps_ssh, "echo ok", timeout=5)
    if not ok:
        vps["reachable"] = False
    else:
        vps["reachable"] = True
        # Git HEAD comparison
        _, vps_head = ssh_cmd(vps_ssh, "cd ~/telegram-claude-bot && git rev-parse --short HEAD 2>/dev/null")
        mac_head = github_mac.get("telegram-claude-bot", {}).get("head", "?")
        vps["vps_head"] = vps_head.strip()
        vps["mac_head"] = mac_head
        vps["git_synced"] = vps_head.strip() == mac_head
        # .env key diff
        mac_env = Path.home() / "telegram-claude-bot" / ".env"
        mac_keys = set()
        if mac_env.exists():
            for line in mac_env.read_text().splitlines():
                l = line.strip()
                if l and not l.startswith("#") and "=" in l:
                    mac_keys.add(l.split("=", 1)[0].strip())
        _, vps_env_text = ssh_cmd(vps_ssh, "cat ~/telegram-claude-bot/.env 2>/dev/null")
        vps_keys = set()
        for line in vps_env_text.splitlines():
            l = line.strip()
            if l and not l.startswith("#") and "=" in l:
                vps_keys.add(l.split("=", 1)[0].strip())
        mac_only = sorted(mac_keys - vps_keys)
        vps_only = sorted(vps_keys - mac_keys)
        vps["env_synced"] = not mac_only and not vps_only
        if mac_only:
            vps["mac_only_keys"] = mac_only
        if vps_only:
            vps["vps_only_keys"] = vps_only
    result["mac_vps"] = vps

    # --- 3. Template ↔ Production sync (hooks/skills on GitHub vs local) ---
    template_prod = {}
    # Hooks: compare local ~/.claude/hooks/ vs claude-curated/hooks/
    local_hooks = Path.home() / ".claude" / "hooks"
    repo_hooks = Path.home() / "claude-curated" / "hooks"
    if local_hooks.exists() and repo_hooks.exists():
        local_only = []
        for f in sorted(local_hooks.glob("auto_*.py")) + sorted(local_hooks.glob("guard_*.py")):
            name = f.name
            found = list(repo_hooks.rglob(name))
            if not found:
                local_only.append(name)
        template_prod["hooks_local_only"] = local_only
        template_prod["hooks_synced"] = len(local_only) == 0
    # Skills: compare local active vs claude-curated/skills/
    repo_skills = Path.home() / "claude-curated" / "skills"
    if repo_skills.exists():
        local_skills = Path.home() / ".claude" / "skills"
        on_github = {p.parent.name for p in repo_skills.rglob("SKILL.md")}
        on_local = {d.name for d in local_skills.iterdir() if d.is_dir() and (d / "SKILL.md").exists()}
        template_prod["skills_github_only"] = sorted(on_github - on_local)
        template_prod["skills_local_only"] = sorted(on_local - on_github)
    result["template_production"] = template_prod

    # --- 4. Content pipeline ---
    content = {}
    drafts_dir = Path.home() / "telegram-claude-bot" / "content_drafts"
    if drafts_dir.exists():
        content["drafts"] = len(list(drafts_dir.glob("2026-*.md")))
        queue = drafts_dir / "queue.md"
        if queue.exists():
            qt = queue.read_text()
            content["queued"] = qt.count("### [") - qt.count("~~POSTED~~")
        else:
            content["queued"] = 0
    result["content"] = content

    return result


# --- Tool 20: voice_control ---
VOICE_LOCK = Path("/tmp/voice_locked")
TTS_MUTE = Path("/tmp/tts_muted")
VAD_MODE = Path("/tmp/vad_mode")


@mcp.tool()
def voice_control(action: str = "status") -> dict:
    """Control voice system — lock/unlock all voice, mute/unmute TTS, check status.

    Args:
        action: "status", "lock", "unlock", "mute", "unmute"
    """
    if action == "lock":
        VOICE_LOCK.touch()
        # Also interrupt any current TTS
        subprocess.run(["pkill", "-f", "afplay.*tts"], capture_output=True)
        return {"voice": "locked", "tts": "stopped"}
    elif action == "unlock":
        VOICE_LOCK.unlink(missing_ok=True)
        return {"voice": "unlocked"}
    elif action == "mute":
        TTS_MUTE.touch()
        subprocess.run(["pkill", "-f", "afplay.*tts"], capture_output=True)
        return {"tts": "muted"}
    elif action == "unmute":
        TTS_MUTE.unlink(missing_ok=True)
        return {"tts": "unmuted"}
    elif action == "status":
        return {
            "voice_locked": VOICE_LOCK.exists(),
            "tts_muted": TTS_MUTE.exists(),
            "vad_mode": VAD_MODE.exists(),
            "voice_daemon": subprocess.run(
                ["pgrep", "-f", "voice_daemon"], capture_output=True
            ).returncode == 0
        }
    return {"error": f"unknown action: {action}"}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
