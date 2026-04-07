#!/usr/bin/env python3
"""Single dispatcher for all PostToolUse hooks (project + global).

Routes by tool_name so only relevant hooks run. Replaces ~25 separate python3 spawns.
"""
import importlib.util
import io
import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parent

# tool_name → list of hook scripts to run
ROUTING = {
    "Edit": [
        "file_unlock.py", "auto_pip_install.py", "auto_memory_index.py",
        "auto_skill_sync.py", "auto_bot_restart.py", "auto_dependency_grep.py",
        "reddit_api_block.py", "mcp_server_restart.py", "reasoning_leak_canary.py",
        # Global guards (Tier 2)
        "admin_only_guard.py", "async_safety_guard.py", "hardcoded_model_guard.py",
        "resource_leak_guard.py", "temp_file_guard.py", "tg_api_guard.py",
        "tg_security_guard.py", "auto_hook_commit.py", "auto_test_after_edit.py",
    ],
    "Write": [
        "file_unlock.py", "auto_memory_index.py", "auto_copyright_header.py",
        "auto_dependency_grep.py",
        # Global guards (Tier 2)
        "admin_only_guard.py", "async_safety_guard.py", "hardcoded_model_guard.py",
        "resource_leak_guard.py", "temp_file_guard.py", "tg_api_guard.py",
        "tg_security_guard.py", "auto_hook_commit.py", "auto_test_after_edit.py",
    ],
    "Bash": [
        "auto_vps_sync.py", "auto_license.py", "auto_repo_check.py",
        "auto_dependency_grep.py", "auto_restart_process.py", "verify_infra.py",
        "revert_memory_chain.py", "pre_commit_validate.py",
    ],
    "Read": [
        "memory_access_tracker.py", "memory_conflict_guard.py",
    ],
    "Skill": [
        "skill_disable_hook.py",
    ],
    "mcp__claude_ai_Gmail__gmail_create_draft": [
        "gmail_humanizer.py",
    ],
}


def load_and_run(script_name, event_data):
    """Import and run a hook's main() function, capturing its stdout."""
    path = HOOKS_DIR / script_name
    if not path.exists():
        return None

    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)

    old_stdin = sys.stdin
    old_stdout = sys.stdout
    sys.stdin = io.StringIO(json.dumps(event_data))
    captured = io.StringIO()
    sys.stdout = captured

    try:
        spec.loader.exec_module(mod)
        if hasattr(mod, "main"):
            mod.main()
    except SystemExit:
        pass
    except Exception:
        pass
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

    output = captured.getvalue().strip()
    if output:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    tool_name = event.get("tool_name", "")

    # Collect hooks to run
    hooks_to_run = []
    if tool_name in ROUTING:
        hooks_to_run.extend(ROUTING[tool_name])

    if not hooks_to_run:
        print("{}")
        return

    # Run hooks, merge results
    merged = {}
    for script in hooks_to_run:
        result = load_and_run(script, event)
        if result:
            # Merge additionalContext
            if "additionalContext" in result:
                if "additionalContext" in merged:
                    merged["additionalContext"] += "\n" + result["additionalContext"]
                else:
                    merged["additionalContext"] = result["additionalContext"]
            # Merge other keys (decision, etc)
            for k, v in result.items():
                if k != "additionalContext":
                    merged[k] = v

    print(json.dumps(merged) if merged else "{}")


if __name__ == "__main__":
    main()
