"""Improvement pattern database for post_task_check."""

import time

# Pattern: (condition_fn, suggestion)
# condition_fn takes list of session actions, returns bool
PATTERNS = [
    {
        "name": "no_commit_after_edits",
        "check": lambda actions: (
            any(a["action"] == "file_edit" for a in actions[-10:])
            and not any(a["action"] == "git_commit" for a in actions[-5:])
            and sum(1 for a in actions[-10:] if a["action"] == "file_edit") >= 3
        ),
        "suggestion": "3+ file edits without a commit. Consider committing before moving on."
    },
    {
        "name": "no_test_after_code",
        "check": lambda actions: (
            any(a["action"] == "file_edit" and a.get("detail", "").endswith(".py") for a in actions[-10:])
            and not any(a["action"] == "test_run" for a in actions[-10:])
        ),
        "suggestion": "Python files edited but no tests run. Consider testing."
    },
    {
        "name": "push_without_sync",
        "check": lambda actions: (
            any(a["action"] == "git_push" for a in actions[-5:])
            and not any(a["action"] == "vps_sync" for a in actions[-3:])
        ),
        "suggestion": "Git pushed but VPS not synced. auto_vps_sync hook should handle this — verify it ran."
    },
    {
        "name": "many_agents_spawned",
        "check": lambda actions: (
            sum(1 for a in actions[-10:] if a["action"] == "agent_spawn") >= 4
        ),
        "suggestion": "4+ agents spawned recently. Check if any duplicated work — use SendMessage to reuse."
    },
    {
        "name": "long_session_no_checkpoint",
        "check": lambda actions: (
            len(actions) > 30
            and not any(a["action"] == "memory_save" for a in actions[-20:])
        ),
        "suggestion": "Long session with no memory saves. Consider saving important findings."
    },
    {
        "name": "config_edit_no_memory_update",
        "check": lambda actions: (
            any(a["action"] == "file_edit" and any(
                k in a.get("detail", "") for k in [".env", "config", "settings"]
            ) for a in actions[-5:])
            and not any(a["action"] == "memory_save" for a in actions[-3:])
        ),
        "suggestion": "Config file edited but no memory update. Check if CLAUDE.md or memory files need updating."
    },
    {
        "name": "content_worthy_no_capture",
        "check": lambda actions: (
            any(a["action"] in ("new_hook", "new_mcp_tool", "new_skill", "architecture_change") for a in actions)
            and not any(a["action"] == "content_capture" for a in actions)
        ),
        "suggestion": "Session produced something novel but nothing saved to content drafts. Use content_capture."
    },
    {
        "name": "unpublished_project",
        "check": lambda actions: (
            any(a["action"] == "file_edit" and "server.py" in a.get("detail", "") for a in actions)
            and not any(a["action"] == "git_push" for a in actions[-10:])
            and not any(a["action"] == "github_publish" for a in actions)
        ),
        "suggestion": "New project code written but not published to GitHub. Consider gh repo create + README."
    },
    {
        "name": "repo_created_no_readme",
        "check": lambda actions: (
            any(a["action"] == "github_publish" for a in actions)
            and not any("readme" in a.get("detail", "").lower() for a in actions)
        ),
        "suggestion": "Repo created but no README written. Call github_readme_sync for tables, then write README."
    },
]


def check_patterns(actions: list) -> list[str]:
    """Run all patterns against session actions, return matching suggestions."""
    if not actions:
        return []

    suggestions = []
    for pattern in PATTERNS:
        try:
            if pattern["check"](actions):
                suggestions.append(pattern["suggestion"])
        except (IndexError, KeyError, TypeError):
            continue

    return suggestions
