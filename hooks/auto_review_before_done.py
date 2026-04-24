#!/usr/bin/env python3
# @bigd-hook-meta
# name: auto_review_before_done
# fires_on: Stop
# always_fire: true
# cost_score: 2
# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""
auto_review_before_done.py — Stop hook

Reads the edit log written by auto_test_after_edit.py (PostToolUse).
Blocking (exit 2): test failures, missing tests
Informational (printed but exit 0): caller impact, schema migration, config/docs drift
Silent (exit 0, no output): everything is fine
"""

import json
import os
import re as _re
import subprocess
import sys
from pathlib import Path

# Skip during convos (auto-clear flow)
_tty = os.environ.get("CLAUDE_TTY_ID", "").strip()
if Path(f"/tmp/claude_ctx_exit_pending_{_tty}").exists() if _tty else Path("/tmp/claude_ctx_exit_pending").exists():
    print("{}")
    sys.exit(0)
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_EDIT_LOG_DIR = Path("/tmp")

_SKIP = _re.compile(
    r"/memory/"
    r"|MEMORY\.md$"
    r"|task_plan\.md$"
    r"|progress\.md$"
    r"|findings\.md$"
    r"|/tests/test_.*\.py$"
    r"|/test_.*\.py$"
    r"|_test\.py$"
)

_CONFIG_NAMES = {"config.py", "llm_client.py", ".env.example", "settings.template.json"}
_DOC_NAMES = {"CLAUDE.md", "ADMIN_HANDBOOK.md", "TERMINAL_MEMORY.md", "README.md"}
_SCHEMA_SIGNALS = ["models.py", "schema.py", "migration", "db_schema", "alembic"]


def _edit_log_path(session_id: str | None) -> Path:
    if session_id:
        safe = session_id.replace("/", "_").replace("\\", "_")
        return _EDIT_LOG_DIR / f"claude_edits_{safe}.json"
    return _EDIT_LOG_DIR / "claude_edits_this_turn.json"


def load_edits(session_id: str | None) -> list:
    """Load edits, keeping only the latest entry per file (last write wins)."""
    path = _edit_log_path(session_id)
    try:
        if path.exists():
            all_edits = json.loads(path.read_text())
            latest: dict = {}
            for e in all_edits:
                f = e["file"]
                if f not in latest or e.get("ts", 0) > latest[f].get("ts", 0):
                    latest[f] = e
            return list(latest.values())
    except Exception:
        pass
    return []


def check_caller_impact(code_edits: list) -> list[str]:
    """Warn about public functions that are referenced in other files."""
    _SKIP_FUNCS = {"check", "action", "main", "run", "setup", "teardown", "handler"}
    warnings = []
    _MAX_GREPS = 5
    _grep_count = 0
    try:
        for e in code_edits:
            if _grep_count >= _MAX_GREPS:
                break
            fp = Path(e["file"])
            if fp.suffix != ".py":
                continue
            funcs = [f for f in e.get("functions", [])
                     if not f.startswith("_") and f not in _SKIP_FUNCS][:2]
            if not funcs:
                continue
            root = fp.parent
            home = Path.home()
            for _ in range(6):
                if (root / ".git").exists() or (root / "pyproject.toml").exists():
                    break
                if root == home or root == root.parent:
                    root = fp.parent
                    break
                root = root.parent
            if root == home:
                continue
            for func in funcs:
                if _grep_count >= _MAX_GREPS:
                    break
                _grep_count += 1
                r = subprocess.run(
                    ["grep", "-rl", "--include=*.py",
                     "--exclude-dir=.git", "--exclude-dir=node_modules",
                     "--exclude-dir=__pycache__", "--exclude-dir=.venv",
                     f"{func}(", str(root)],
                    capture_output=True, text=True, timeout=1
                )
                callers = [
                    c for c in r.stdout.strip().splitlines()
                    if c and c != str(fp)
                    and "/test_" not in c and "/__pycache__/" not in c
                ]
                if callers:
                    names = ", ".join(Path(c).name for c in callers[:3])
                    warnings.append(f"  {func}() → {names}")
    except Exception:
        pass
    return warnings


def check_schema_migration(code_edits: list) -> list[str]:
    """Warn if schema/model files were edited without a migration."""
    warnings = []
    for e in code_edits:
        if any(s in e["file"].lower() for s in _SCHEMA_SIGNALS):
            warnings.append(f"  {Path(e['file']).name} — migration needed?")
    return warnings


def check_config_docs_sync(code_edits: list) -> list[str]:
    """Warn if config changed but no docs were updated this turn."""
    edited_names = {Path(e["file"]).name for e in code_edits}
    config_hit = edited_names & _CONFIG_NAMES
    if config_hit and not (edited_names & _DOC_NAMES):
        return [f"  {', '.join(config_hit)} changed — docs (CLAUDE.md/README) may need update"]
    return []


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    session_id = data.get("session_id")
    edits = load_edits(session_id)
    if not edits:
        sys.exit(0)

    code_edits = [e for e in edits if not _SKIP.search(e["file"])]
    if not code_edits:
        sys.exit(0)

    # ── Blocking checks ───────────────────────────────────────────────────────
    failed_tests = [e["file"] for e in code_edits if e.get("tests_passed") is False]

    missing_tests = []
    try:
        from test_helpers import find_test_file, should_require_tests
        seen: set = set()
        for e in code_edits:
            fp = Path(e["file"])
            if fp in seen or fp.suffix != ".py":
                continue
            seen.add(fp)
            needs = e.get("needs_tests") if e.get("needs_tests") is not None else should_require_tests(fp)
            if needs and e.get("tests_passed") is None and find_test_file(fp) is None:
                missing_tests.append(fp.name)
    except ImportError:
        pass

    # ── Informational checks (never block) ────────────────────────────────────
    caller_warnings = check_caller_impact(code_edits)
    schema_warnings = check_schema_migration(code_edits)
    config_warnings = check_config_docs_sync(code_edits)
    info_warnings = caller_warnings + schema_warnings + config_warnings

    # Completely silent when nothing to report
    if not failed_tests and not missing_tests and not info_warnings:
        _edit_log_path(session_id).write_text("[]")
        sys.exit(0)

    # Build output
    file_list = "\n".join(f"  - {e['file']}" for e in code_edits)
    out = f"Files edited:\n{file_list}"

    if failed_tests:
        out += "\n\n❌ FAILING TESTS — fix before finishing:"
        for f in failed_tests:
            out += f"\n  {Path(f).name}"

    if missing_tests:
        out += "\n\n⚠️  MISSING TESTS — write before finishing:"
        for f in missing_tests:
            out += f"\n  {f}"

    if caller_warnings:
        out += "\n\n📎 Caller impact (verify these still work):"
        out += "\n" + "\n".join(caller_warnings)

    if schema_warnings:
        out += "\n\n🗄️  Schema changes:"
        out += "\n" + "\n".join(schema_warnings)

    if config_warnings:
        out += "\n\n📄 Config/docs drift:"
        out += "\n" + "\n".join(config_warnings)

    print(out, file=sys.stderr)

    try:
        _edit_log_path(session_id).write_text("[]")
    except Exception:
        pass

    # Only block on actual test failures/missing tests
    sys.exit(2 if (failed_tests or missing_tests) else 0)


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent))
    from _safe_hook import safe_run
    safe_run(main, "auto_review_before_done")
