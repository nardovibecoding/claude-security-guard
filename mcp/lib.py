"""Shared library — pure Python functions usable by both MCP server and admin bot.

No MCP dependency. Import freely from any Python project:
    from lib import content_capture, content_queue, session_checkpoint
"""

import time
from collections import deque
from datetime import datetime
from pathlib import Path

# --- Paths ---
CONTENT_DRAFTS = Path.home() / "telegram-claude-bot" / "content_drafts"
CONTENT_LOG = CONTENT_DRAFTS / "running_log.md"
QUEUE_FILE = CONTENT_DRAFTS / "queue.md"
CHECKPOINT_DIR = CONTENT_DRAFTS

# --- Session state (in-memory, resets on process restart) ---
session_actions = deque(maxlen=100)


# --- Content capture ---
def content_capture(moment: str, category: str = "insight") -> dict:
    """Save a content-worthy moment to the running draft log.

    Args:
        moment: the insight, discovery, result, or aha moment
        category: one of: insight, result, code, number, journey, mistake
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    CONTENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = f"\n## [{category}] {ts}\n{moment}\n"
    with open(CONTENT_LOG, "a") as f:
        f.write(entry)
    return {"saved": True, "file": str(CONTENT_LOG), "category": category}


# --- Content queue ---
def content_queue(action: str = "list", tweet: str = "", priority: str = "normal") -> dict:
    """Manage tweet draft queue. Add drafts, list queue, get next to post.

    Args:
        action: "add", "list", "next", or "posted"
        tweet: tweet text (required for "add")
        priority: "high", "normal", "low" (for "add")
    """
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not QUEUE_FILE.exists():
        QUEUE_FILE.write_text("# Tweet Queue\n\n")

    content = QUEUE_FILE.read_text()

    if action == "add":
        if not tweet:
            return {"error": "provide tweet text"}
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n### [{priority}] {ts}\n{tweet}\n"
        with open(QUEUE_FILE, "a") as f:
            f.write(entry)
        items = content.count("### [")
        return {"queued": True, "position": items + 1, "priority": priority}

    elif action == "list":
        items = []
        for block in content.split("### [")[1:]:
            prio = block.split("]")[0]
            rest = block.split("]", 1)[1].strip()
            date_line = rest.split("\n")[0].strip()
            text = "\n".join(rest.split("\n")[1:]).strip()
            items.append({"priority": prio, "date": date_line, "text": text[:200]})
        return {"queue": items, "total": len(items)}

    elif action == "next":
        items = []
        for block in content.split("### [")[1:]:
            if "~~POSTED~~" in block:
                continue
            prio = block.split("]")[0]
            rest = block.split("]", 1)[1].strip()
            text = "\n".join(rest.split("\n")[1:]).strip()
            prio_score = {"high": 3, "normal": 2, "low": 1}.get(prio, 0)
            items.append({"priority": prio, "score": prio_score, "text": text})
        if not items:
            return {"queue_empty": True}
        items.sort(key=lambda x: x["score"], reverse=True)
        return {"next": items[0]["text"], "priority": items[0]["priority"], "remaining": len(items)}

    elif action == "posted":
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("### [") and "~~POSTED~~" not in line:
                lines[i] = line + " ~~POSTED~~"
                QUEUE_FILE.write_text("\n".join(lines))
                return {"marked": True}
        return {"error": "no unposted items"}

    return {"error": f"unknown action: {action}"}


# --- Session checkpoint ---
def session_checkpoint(summary: str, key_decisions: list = None, files_changed: list = None) -> dict:
    """Save session state to checkpoint file.

    Args:
        summary: what was accomplished (2-3 sentences)
        key_decisions: important decisions made
        files_changed: key files created or modified
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"checkpoint_{ts}.md"

    actions = list(session_actions)
    file_content = f"""# Session Checkpoint — {ts}

## Summary
{summary}

## Key Decisions
{chr(10).join(f'- {d}' for d in (key_decisions or [])) or '(none)'}

## Files Changed
{chr(10).join(f'- {f}' for f in (files_changed or [])) or '(none)'}

## Session Actions ({len(actions)} total)
{chr(10).join(f'- [{a.get("action")}] {a.get("detail", "")}' for a in actions[-20:]) or '(none)'}

## Resume Context
Pick up from here next session. Key state:
- {summary}
"""
    checkpoint_path.write_text(file_content)

    if len(actions) > 10:
        content_capture(moment=f"Productive session: {summary}", category="journey")

    return {"saved": str(checkpoint_path), "actions_logged": len(actions)}


# --- Session log ---
def session_log(action: str = "", detail: str = "", query: bool = False) -> dict:
    """Log a session action or query the log.

    Args:
        action: action type (e.g. "git_push", "file_edit", "agent_spawn")
        detail: additional detail
        query: if True, return the log instead of appending
    """
    if query:
        return {"actions": list(session_actions)[-20:]}

    if action:
        session_actions.append({
            "action": action,
            "detail": detail,
            "timestamp": time.time()
        })
        return {"logged": True, "total": len(session_actions)}

    return {"error": "provide action or set query=True"}


# --- Git commit+push (async helper for admin bot) ---
def git_commit_push_async(message: str = "auto: content update"):
    """Commit and push content_drafts changes. Non-blocking."""
    import subprocess
    import threading

    def _do():
        repo = str(Path.home() / "telegram-claude-bot")
        subprocess.run(["git", "-C", repo, "add", "content_drafts/"], capture_output=True)
        subprocess.run(["git", "-C", repo, "commit", "-m", message], capture_output=True)
        subprocess.run(["git", "-C", repo, "push"], capture_output=True)

    threading.Thread(target=_do, daemon=True).start()
