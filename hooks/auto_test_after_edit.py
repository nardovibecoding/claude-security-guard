#!/usr/bin/env python3
# @bigd-hook-meta
# name: auto_test_after_edit
# fires_on: PostToolUse
# relevant_intents: [code, debug, meta]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, vps, sync, memory]
# cost_score: 3
# always_fire: false
"""
auto_test_after_edit.py — PostToolUse hook
Auto-runs syntax/test checks after any Edit/Write/MultiEdit.
Claude sees the result and MUST fix failures before saying "done".

Checks by file type:
  .py   → python3 -m py_compile (always) + pytest if test file exists
  .sh   → bash -n (syntax check)
  .json → json.load (parse check)
  .js   → node --check (if node available)
  other → skip silently
"""

import io
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_EDIT_LOG = Path("/tmp/claude_edits_this_turn.json")


def run(cmd, timeout=15):
    """Run command, return (ok, output)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {timeout}s"
    except FileNotFoundError:
        return None, f"Command not found: {cmd[0]}"


def find_test_file(file_path: Path):
    """Look for a pytest test file corresponding to the edited file."""
    name = file_path.stem  # e.g. "bot_base"
    parent = file_path.parent
    candidates = [
        parent / f"test_{name}.py",
        parent / "tests" / f"test_{name}.py",
        parent.parent / "tests" / f"test_{name}.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


_PROJECT = Path.home() / "telegram-claude-bot"

# Model names that must only appear in llm_client.py
_MODEL_PATTERNS = [
    "MiniMax-M2.5", "MiniMax-M2.7", "kimi-k2", "deepseek-chat",
    "llama-3.3-70b", "gemini-2.0-flash", "qwen3-32b",
]


def check_hook_reload(file_path: Path):
    """Warn user to /clear if a hook file was edited."""
    hooks_dir = Path.home() / ".claude" / "hooks"
    if file_path.parent == hooks_dir or (
        str(file_path).startswith(str(_PROJECT / "hooks"))
        and file_path.suffix == ".py"
    ):
        return (
            "⚠️  Hook file edited — run /clear or start a new session "
            "to pick up changes. Hooks are loaded once at session start."
        )
    return None


def check_hardcoded_models(file_path: Path):
    """Warn if a non-llm_client file hardcodes model names."""
    if file_path.name == "llm_client.py":
        return None
    if not str(file_path).startswith(str(_PROJECT)):
        return None
    try:
        content = file_path.read_text()
    except Exception:
        return None
    found = [m for m in _MODEL_PATTERNS if m in content]
    if found:
        return (
            f"⚠️  Hardcoded model name(s) in {file_path.name}: "
            f"{', '.join(found)}. Import from llm_client.py instead."
        )
    return None


def check_python(file_path: Path):
    """Syntax check + ruff lint + mypy types + optional pytest."""
    results = []

    # 0. Hook reload nudge
    hook_warn = check_hook_reload(file_path)
    if hook_warn:
        results.append(hook_warn)

    # 0b. Hardcoded model name check
    model_warn = check_hardcoded_models(file_path)
    if model_warn:
        results.append(model_warn)

    # 1. Syntax check (fast, always)
    ok, out = run([sys.executable, "-m", "py_compile", str(file_path)])
    if ok is None:
        results.append("⚠️  py_compile not available")
    elif ok:
        results.append(f"✅ Syntax OK: {file_path.name}")
    else:
        results.append(f"❌ Syntax error in {file_path.name}:\n{out}")
        return "\n".join(results)  # stop here, no point continuing

    # 2. Ruff lint — catches logic smells: unused vars, unreachable code,
    #    shadowed builtins, mutable defaults, broad excepts, etc.
    ok, out = run(["ruff", "check", "--select=E,F,W,B,C4,SIM,RUF", str(file_path)])
    if ok is None:
        pass  # ruff not installed, skip
    elif ok:
        results.append(f"✅ Lint clean: {file_path.name}")
    else:
        # Filter to real issues (skip E501 line-length noise)
        issues = [l for l in out.splitlines() if "E501" not in l and l.strip()]
        if issues:
            results.append(f"⚠️  Lint issues in {file_path.name}:\n" + "\n".join(issues[:15]))

    # 3. Mypy type check — catches wrong arg types, missing returns, etc.
    ok, out = run(
        ["mypy", "--ignore-missing-imports", "--no-error-summary", str(file_path)],
        timeout=20,
    )
    if ok is None:
        pass  # mypy not installed, skip
    elif not ok and out:
        errors = [l for l in out.splitlines() if ": error:" in l]
        if errors:
            results.append(f"⚠️  Type errors in {file_path.name}:\n" + "\n".join(errors[:10]))

    # 4. pytest if test file exists
    test_file = find_test_file(file_path)
    if test_file:
        ok, out = run(
            [sys.executable, "-m", "pytest", str(test_file), "-x", "-q", "--tb=short"],
            timeout=30,
        )
        if ok:
            summary = out.strip().split("\n")[-1] if out else "passed"
            results.append(f"✅ Tests passed: {summary}")
        else:
            results.append(f"❌ Tests FAILED ({test_file.name}):\n{out}")

    return "\n".join(results)


def check_shell(file_path: Path):
    ok, out = run(["bash", "-n", str(file_path)])
    if ok is None:
        return f"⚠️  bash not available for syntax check"
    if ok:
        return f"✅ Shell syntax OK: {file_path.name}"
    return f"❌ Shell syntax error in {file_path.name}:\n{out}"


def check_json(file_path: Path):
    try:
        json.loads(file_path.read_text())
        return f"✅ JSON valid: {file_path.name}"
    except json.JSONDecodeError as e:
        return f"❌ JSON invalid in {file_path.name}: {e}"
    except Exception as e:
        return f"⚠️  Could not read {file_path.name}: {e}"


def check_js(file_path: Path):
    ok, out = run(["node", "--check", str(file_path)])
    if ok is None:
        return None  # node not available, skip silently
    if ok:
        return f"✅ JS syntax OK: {file_path.name}"
    return f"❌ JS syntax error in {file_path.name}:\n{out}"


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)
    if not file_path.exists():
        sys.exit(0)

    suffix = file_path.suffix.lower()

    result = None
    if suffix == ".py":
        result = check_python(file_path)
    elif suffix == ".sh":
        result = check_shell(file_path)
    elif suffix == ".json":
        result = check_json(file_path)
    elif suffix in (".js", ".mjs", ".cjs"):
        result = check_js(file_path)

    if result:
        print(result)

    # Log this edit so the Stop hook can trigger a logic review + test enforcement
    try:
        from test_helpers import extract_functions, should_require_tests
        funcs = extract_functions(file_path) if file_path.suffix == ".py" else []
        needs_tests = should_require_tests(file_path)
    except Exception:
        funcs, needs_tests = [], False

    try:
        existing = json.loads(_EDIT_LOG.read_text()) if _EDIT_LOG.exists() else []
        existing.append({
            "file": file_path_str,
            "ts": datetime.now().timestamp(),
            "functions": funcs,
            "needs_tests": needs_tests,
        })
        _EDIT_LOG.write_text(json.dumps(existing))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    _raw = sys.stdin.read()
    try:
        _prompt = json.loads(_raw).get("prompt", "") if _raw else ""
    except Exception:
        _prompt = ""
    from _semantic_router import should_fire
    if not should_fire(__file__, _prompt):
        print("{}")
        sys.exit(0)
    sys.stdin = io.StringIO(_raw)
    main()
