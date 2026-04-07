#!/usr/bin/env python3
"""Single dispatcher for all PreToolUse hooks (project + global).

Routes by tool_name so only relevant hooks run. Replaces ~15 separate python3 spawns.
"""
import importlib.util
import json
import sys
import io
from pathlib import Path

HOOKS_DIR = Path(__file__).parent

# tool_name → list of hook scripts
ROUTING = {
    "Bash": [
        "guard_safety.py", "auto_pre_publish.py", "unicode_grep_warn.py",
        "vps_setup_guard.py",
    ],
    "Edit": [
        "guard_safety.py", "file_lock.py", "pre_edit_impact.py",
        "skill_disable_not_delete.py", "memory_conflict_guard.py",
    ],
    "Write": [
        "guard_safety.py", "file_lock.py", "skill_disable_not_delete.py",
        "memory_conflict_guard.py",
    ],
    "Grep": [
        "unicode_grep_warn.py", "auto_recall.py",
    ],
    "Glob": [
        "auto_recall.py",
    ],
    "Agent": [
        "agent_cascade_guard.py", "agent_count_guard.py",
        "agent_simplicity_guard.py", "agent_tracker.py",
    ],
    "Skill": [
        "skill_enable_hook.py",
    ],
    "mcp__plugin_telegram_telegram__reply": [
        "tg_qr_document.py",
    ],
}

# Hooks that check tool_input content, not just tool_name — run on specific tools only
TOOL_INPUT_HOOKS = {
    "api_key_lookup.py": ["Bash", "Grep", "Read"],
}


def load_and_run(script_name, event_data):
    """Import and run a hook's main(), capturing stdout."""
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

    # Add tool-input hooks that match this tool
    for script, tools in TOOL_INPUT_HOOKS.items():
        if tool_name in tools:
            hooks_to_run.append(script)

    if not hooks_to_run:
        print("{}")
        return

    # Run hooks, merge results — stop on block/deny
    merged = {}
    for script in hooks_to_run:
        result = load_and_run(script, event)
        if result:
            # If any hook blocks, return immediately
            decision = result.get("decision", "")
            if decision in ("block", "deny"):
                print(json.dumps(result))
                return

            if "additionalContext" in result:
                if "additionalContext" in merged:
                    merged["additionalContext"] += "\n" + result["additionalContext"]
                else:
                    merged["additionalContext"] = result["additionalContext"]
            for k, v in result.items():
                if k != "additionalContext":
                    merged[k] = v

    print(json.dumps(merged) if merged else "{}")


if __name__ == "__main__":
    main()
