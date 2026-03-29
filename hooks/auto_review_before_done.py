#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""
auto_review_before_done.py — Stop hook
Fires before Claude ends its turn. Two enforcement layers:

1. LOGIC REVIEW — if files were edited, injects a self-review checklist
   (root cause, edge cases, callers, side effects, behavior match)

2. TEST ENFORCEMENT — for testable Python files, checks that:
   - A test file exists with tests covering the changed functions
   - Tests actually pass
   If tests are missing, blocks Claude and demands tests before "done".

Exit 2 = block Claude from ending turn.
Exit 0 = allow turn to end normally.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

_EDIT_LOG = Path("/tmp/claude_edits_this_turn.json")


def load_edits():
    try:
        if _EDIT_LOG.exists():
            data = json.loads(_EDIT_LOG.read_text())
            now = datetime.now().timestamp()
            recent = [e for e in data if now - e.get("ts", 0) < 600]
            return recent
    except Exception:
        pass
    return []


def _run_pytest(test_file: Path, timeout: int = 30) -> tuple[bool, str]:
    """Run pytest on a test file, return (passed, output)."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-x", "-q", "--tb=short"],
            capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


def _check_tests(edits: list[dict]) -> str | None:
    """Check test coverage for edited files. Returns message or None."""
    try:
        from test_helpers import (
            find_test_file, check_test_coverage,
            should_require_tests, test_file_path_for
        )
    except ImportError:
        return None  # test_helpers not available, skip

    testable_files = []
    for edit in edits:
        fp = Path(edit["file"])
        if not fp.suffix == ".py":
            continue
        # Use cached needs_tests from PostToolUse or compute fresh
        needs = edit.get("needs_tests")
        if needs is None:
            needs = should_require_tests(fp)
        if needs:
            testable_files.append(fp)

    if not testable_files:
        return None

    # Deduplicate
    testable_files = list(dict.fromkeys(testable_files))

    missing_tests = []
    failing_tests = []
    passing_tests = []

    for source in testable_files:
        test_file = find_test_file(source)

        if test_file is None:
            # No test file at all — collect missing functions
            funcs = []
            for edit in edits:
                if edit["file"] == str(source):
                    funcs = edit.get("functions", [])
                    break
            expected_path = test_file_path_for(source)
            missing_tests.append({
                "source": source.name,
                "functions": funcs[:8],  # cap display
                "test_path": str(expected_path),
            })
        else:
            # Test file exists — check coverage and run
            coverage = check_test_coverage(source, test_file)
            if coverage["missing"]:
                missing_tests.append({
                    "source": source.name,
                    "functions": coverage["missing"][:8],
                    "test_path": str(test_file),
                    "has_file": True,
                })

            # Run existing tests
            if coverage["test_count"] > 0:
                passed, output = _run_pytest(test_file)
                if passed:
                    passing_tests.append(f"  {test_file.name}: {coverage['test_count']} tests passed")
                else:
                    failing_tests.append(f"  {test_file.name}:\n{output}")

    if not missing_tests and not failing_tests:
        if passing_tests:
            return "TEST STATUS:\n" + "\n".join(passing_tests)
        return None  # nothing to report

    # Build enforcement message
    parts = []

    if missing_tests:
        parts.append("TESTS NEEDED — write tests before finishing:")
        for m in missing_tests:
            funcs_str = ", ".join(m["functions"]) if m["functions"] else "(all public functions)"
            if m.get("has_file"):
                parts.append(f"  {m['source']}: add tests for {funcs_str} in {m['test_path']}")
            else:
                parts.append(f"  {m['source']}: create {m['test_path']} with tests for {funcs_str}")

    if failing_tests:
        parts.append("\nFAILING TESTS — fix before finishing:")
        parts.extend(failing_tests)

    if passing_tests:
        parts.append("\nPassing:")
        parts.extend(passing_tests)

    return "\n".join(parts)


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    if data.get("event") not in ("Stop", None):
        pass

    edits = load_edits()
    if not edits:
        sys.exit(0)

    edited_files = list(dict.fromkeys(e["file"] for e in edits))

    # Skip review for memory/docs-only edits (no code changes)
    code_edits = [f for f in edited_files
                  if not ("/memory/" in f or f.endswith("MEMORY.md")
                          or f.endswith("task_plan.md")
                          or f.endswith("progress.md")
                          or f.endswith("findings.md"))]
    if not code_edits:
        sys.exit(0)
    file_list = "\n".join(f"  - {f}" for f in edited_files)

    # Layer 1: Logic review checklist
    review = f"""
+------------------------------------------------------+
|  LOGIC REVIEW — before you say "done"                |
+------------------------------------------------------+

You edited these files this turn:
{file_list}

Before reporting complete, verify each change:

1. ROOT CAUSE — Did you fix the actual cause, or just suppress the symptom?
2. EDGE CASES — Empty input? None values? Concurrent calls? Large data?
3. CALLERS — Do all callers of changed functions still work correctly?
4. SIDE EFFECTS — Any shared state, globals, or DB writes affected?
5. BEHAVIOR MATCH — Does the result match exactly what Bernard asked for?
""".strip()

    # Layer 2: Test enforcement
    test_msg = _check_tests(edits)

    output = review
    if test_msg:
        output += f"\n\n+------------------------------------------------------+\n"
        output += f"|  TEST ENFORCEMENT                                    |\n"
        output += f"+------------------------------------------------------+\n\n"
        output += test_msg

    print(output, file=sys.stderr)

    # Clear the edit log
    try:
        _EDIT_LOG.write_text("[]")
    except Exception:
        pass

    # Exit 2 = block Claude from ending turn
    sys.exit(2)


if __name__ == "__main__":
    main()
