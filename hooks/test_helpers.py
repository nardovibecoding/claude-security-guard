#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""
test_helpers.py — Utilities for functional test enforcement.

Used by auto_test_after_edit.py and auto_review_before_done.py to:
- Extract function/class names from Python files (ast-based)
- Discover existing test files
- Check which functions have tests
- Generate pytest test stubs for untested functions

Cross-platform (macOS + Linux), pure stdlib (no external deps).
"""

import ast
import re
from pathlib import Path

# Files that never need tests (pattern-based)
_SKIP_PATTERNS = [
    r"__init__\.py$",
    r"__main__\.py$",
    r"conftest\.py$",
    r"test_.*\.py$",        # test files themselves
    r"\.?config.*\.py$",    # config files
    r"vps_config\.py$",
    r"setup\.py$",
    r"manage\.py$",
]
_SKIP_RE = re.compile("|".join(_SKIP_PATTERNS))

# Directories to skip
_SKIP_DIRS = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".tox", ".mypy_cache"}

# Minimum function count to warrant tests
_MIN_FUNCTIONS = 1


def should_require_tests(file_path: Path) -> bool:
    """Decide if a file should have corresponding tests.

    Returns False for config files, __init__.py, test files themselves,
    files inside venv/node_modules, files with no real functions, and
    files under 10 lines.
    """
    if not file_path.suffix == ".py":
        return False

    # Skip by name pattern
    if _SKIP_RE.search(file_path.name):
        return False

    # Skip if inside excluded directories
    parts = file_path.parts
    if any(d in parts for d in _SKIP_DIRS):
        return False

    # Skip tiny files (constants-only, etc.)
    try:
        lines = file_path.read_text().splitlines()
        if len(lines) < 10:
            return False
    except Exception:
        return False

    # Must have at least one real function
    funcs = extract_functions(file_path)
    return len(funcs) >= _MIN_FUNCTIONS


def extract_functions(file_path: Path) -> list[str]:
    """Extract public function and method names from a Python file using AST.

    Returns names of:
    - Top-level functions (not starting with _)
    - Class methods (not starting with __)
    Skips dunder methods, private helpers, and decorators-only functions.
    """
    try:
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError):
        return []

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            name = node.name
            # Skip dunders and private
            if name.startswith("__") and name.endswith("__"):
                continue
            # Skip main() — it's an entry point, not testable logic
            if name == "main":
                continue
            # Include public and single-underscore (internal but testable)
            functions.append(name)
    return sorted(set(functions))


def extract_classes(file_path: Path) -> list[str]:
    """Extract class names from a Python file."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError):
        return []

    return [node.name for node in ast.iter_child_nodes(tree)
            if isinstance(node, ast.ClassDef)]


def find_test_file(source_path: Path) -> Path | None:
    """Find a test file corresponding to a source file.

    Search order:
    1. tests/test_{name}.py (sibling tests/ dir)
    2. test_{name}.py (same dir)
    3. ../tests/test_{name}.py (parent tests/ dir)
    4. tests/test_{name}.py (project root tests/ dir)
    """
    name = source_path.stem
    parent = source_path.parent
    candidates = [
        parent / "tests" / f"test_{name}.py",
        parent / f"test_{name}.py",
        parent.parent / "tests" / f"test_{name}.py",
    ]

    # Also check project root (walk up to find .git)
    root = _find_project_root(source_path)
    if root:
        candidates.append(root / "tests" / f"test_{name}.py")

    for c in candidates:
        if c.exists():
            return c
    return None


def _find_project_root(path: Path) -> Path | None:
    """Walk up to find project root (has .git or pyproject.toml)."""
    current = path.parent
    for _ in range(10):
        if (current / ".git").exists() or (current / "pyproject.toml").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def check_test_coverage(source_path: Path, test_path: Path) -> dict:
    """Check which functions from source have tests in the test file.

    Returns: {
        "covered": ["func_a", "func_b"],
        "missing": ["func_c"],
        "test_count": 5
    }
    """
    source_funcs = extract_functions(source_path)
    if not source_funcs:
        return {"covered": [], "missing": [], "test_count": 0}

    try:
        test_source = test_path.read_text().lower()
    except OSError:
        return {"covered": [], "missing": source_funcs, "test_count": 0}

    # Count test functions
    try:
        test_tree = ast.parse(test_path.read_text())
        test_count = sum(
            1 for node in ast.walk(test_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    except SyntaxError:
        test_count = 0

    covered = []
    missing = []
    for func in source_funcs:
        # Check if the function is referenced in test file
        # Patterns: test_{func}, {func}(, from ... import {func}
        func_lower = func.lower()
        if (f"test_{func_lower}" in test_source or
                f"{func_lower}(" in test_source or
                f"import {func_lower}" in test_source or
                f", {func_lower}" in test_source):
            covered.append(func)
        else:
            missing.append(func)

    return {"covered": covered, "missing": missing, "test_count": test_count}


def generate_test_stub(source_path: Path, functions: list[str] | None = None) -> str:
    """Generate a pytest test stub for the given source file.

    If functions is None, generates stubs for all extracted functions.
    The stub is importable and runnable — Claude fills in assertions.
    """
    name = source_path.stem
    if functions is None:
        functions = extract_functions(source_path)
    classes = extract_classes(source_path)

    # Build relative import path
    root = _find_project_root(source_path)
    if root:
        try:
            rel = source_path.relative_to(root)
            module = ".".join(rel.with_suffix("").parts)
        except ValueError:
            module = name
    else:
        module = name

    lines = [
        f'"""Tests for {name}.py — auto-generated stub, fill in assertions."""',
        "import pytest",
        "import sys",
        "from pathlib import Path",
        "",
        "# Add project root to path for imports",
        f'sys.path.insert(0, str(Path(__file__).resolve().parent.parent))',
        "",
    ]

    # Try to import the module
    lines.append(f"# Import the module under test")
    if functions:
        func_imports = ", ".join(functions[:10])  # cap at 10 for readability
        lines.append(f"try:")
        lines.append(f"    from {module} import {func_imports}")
        lines.append(f"except ImportError:")
        lines.append(f"    # Module has external deps — test what you can")
        lines.append(f"    pass")
    lines.append("")

    # Generate test stubs for each function
    for func in functions:
        lines.extend([
            "",
            f"def test_{func}():",
            f'    """Test {func} function."""',
            f"    # TODO: Add actual test assertions",
            f"    # Example: result = {func}(...)",
            f"    # assert result == expected",
            f"    pass",
        ])

    # If classes exist, add class test stubs
    for cls in classes:
        lines.extend([
            "",
            f"class Test{cls}:",
            f'    """Tests for {cls} class."""',
            "",
            f"    def test_init(self):",
            f"        # TODO: Test {cls} initialization",
            f"        pass",
        ])

    lines.append("")
    return "\n".join(lines)


def test_file_path_for(source_path: Path) -> Path:
    """Return the expected test file path for a source file.

    Creates in tests/ subdir of the source file's directory.
    """
    return source_path.parent / "tests" / f"test_{source_path.stem}.py"
