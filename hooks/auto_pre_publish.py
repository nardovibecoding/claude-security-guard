# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
#!/usr/bin/env python3
"""PreToolUse hook: block gh repo visibility public until all checks pass.

Intercepts:
  gh repo edit --visibility public
  gh repo create --public

Runs 12 checks: secrets, license, gitignore, artifacts, binaries, NOTICE, copyright headers.
"""
import json
import re
import subprocess
import sys
from pathlib import Path


def check(tool_name: str, tool_input: dict, input_data: dict) -> bool:
    """Return True if this is a 'make repo public' command."""
    if tool_name != "Bash":
        return False
    cmd = tool_input.get("command", "")
    return bool(
        ("--visibility public" in cmd and "gh repo" in cmd)
        or ("gh repo create" in cmd and "--public" in cmd)
    )


def action(tool_name: str, tool_input: dict, input_data: dict) -> dict:
    """Run pre-publish audit. Block if critical issues found."""
    cmd = tool_input.get("command", "")

    # Find repo path from command or cwd
    repo_path = _find_repo_path()
    if not repo_path or not repo_path.exists():
        return {"decision": "block", "reason": "Could not determine repo path. cd into the repo first."}

    issues = []
    warnings = []

    # --- CRITICAL checks (block) ---

    # 1. Secret scan: hardcoded IPs, API keys, tokens
    secret_patterns = [
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "Hardcoded IP address"),
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI key"),
        (r'sk-ant-[a-zA-Z0-9-]{20,}', "Anthropic key"),
        (r'ghp_[a-zA-Z0-9]{36}', "GitHub PAT"),
        (r'AKIA[A-Z0-9]{16}', "AWS key"),
        (r'xoxb-[a-zA-Z0-9-]+', "Slack token"),
        (r'AIza[a-zA-Z0-9_-]{35}', "Google key"),
        (r'-----BEGIN.*PRIVATE KEY-----', "Private key"),
        (r'password\s*[:=]\s*["\'][^"\']{8,}', "Hardcoded password"),
    ]
    tracked = _git_tracked_files(repo_path)
    for f in tracked:
        if f.suffix in {'.pyc', '.png', '.jpg', '.gif', '.ico', '.woff', '.ttf', '.lock'}:
            continue
        try:
            content = f.read_text(errors='replace')
        except Exception:
            continue
        for pattern, desc in secret_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                # Skip common false positives
                if desc == "Hardcoded IP address" and match in ("0.0.0.0", "127.0.0.1", "255.255.255.255", "192.168.0.1"):
                    continue
                issues.append(f"SECRET: {desc} in {f.name}: {match[:20]}...")
                break  # one per file per pattern

    # 2. Personal paths
    personal_patterns = [
        (r'/Users/[a-zA-Z]+/', "macOS user path"),
        (r'/home/[a-zA-Z]+/', "Linux home path"),
        (r'-Users-[a-zA-Z]+', "Claude project path with username"),
        (r'-home-[a-zA-Z]+', "Claude project path with username"),
    ]
    for f in tracked:
        if f.suffix in {'.pyc', '.png', '.jpg', '.gif', '.ico', '.woff', '.ttf', '.lock'}:
            continue
        try:
            content = f.read_text(errors='replace')
        except Exception:
            continue
        for pattern, desc in personal_patterns:
            if re.search(pattern, content):
                if f.name not in ('.gitignore', 'LICENSE', 'NOTICE'):
                    issues.append(f"PERSONAL: {desc} in {f.name}")
                    break

    # 3. LICENSE has full text (not just copyright line)
    license_file = repo_path / "LICENSE"
    if not license_file.exists():
        issues.append("LICENSE: file missing")
    else:
        license_text = license_file.read_text()
        if len(license_text.strip().splitlines()) < 10:
            issues.append("LICENSE: only copyright line, no license text")

    # 4. Telegram chat IDs / bot tokens
    for f in tracked:
        if f.suffix in {'.pyc', '.png', '.jpg', '.gif', '.ico', '.woff', '.ttf', '.lock'}:
            continue
        try:
            content = f.read_text(errors='replace')
        except Exception:
            continue
        if re.search(r'-100\d{10,}', content):
            issues.append(f"SECRET: Telegram chat_id in {f.name}")
        if re.search(r'\d{9,}:[A-Za-z0-9_-]{35}', content):
            issues.append(f"SECRET: Telegram bot token in {f.name}")

    # --- HIGH checks (block) ---

    # 5. .gitignore exists
    if not (repo_path / ".gitignore").exists():
        issues.append("MISSING: .gitignore — risk of .env, .DS_Store, __pycache__ leaks")

    # 6. NOTICE file exists (AGPL)
    if not (repo_path / "NOTICE").exists():
        issues.append("MISSING: NOTICE file (required for AGPL-3.0)")

    # 7. No .DS_Store committed
    for f in tracked:
        if f.name == ".DS_Store":
            issues.append(f"ARTIFACT: .DS_Store committed at {f.relative_to(repo_path)}")

    # 8. No __pycache__ committed
    for f in tracked:
        if "__pycache__" in str(f):
            issues.append(f"ARTIFACT: __pycache__ committed at {f.relative_to(repo_path)}")
            break

    # --- MEDIUM checks (block) ---

    # 9. GitHub description and topics (if repo exists on GitHub)
    repo_name = repo_path.name
    try:
        r = subprocess.run(
            ["gh", "repo", "view", f"nardovibecoding/{repo_name}", "--json", "description,repositoryTopics"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            import json as _json
            meta = _json.loads(r.stdout)
            if not meta.get("description"):
                issues.append("GITHUB: no description set — invisible in search")
            topics = meta.get("repositoryTopics", [])
            if not topics:
                issues.append("GITHUB: no topics set — poor discoverability")
    except Exception:
        pass

    # --- LOW checks (warn) ---

    # 10. No large binaries (>1MB)
    for f in tracked:
        try:
            if f.stat().st_size > 1_000_000:
                warnings.append(f"LARGE: {f.name} ({f.stat().st_size // 1024}KB)")
        except Exception:
            pass

    # 10. README exists and has substance
    readme = repo_path / "README.md"
    if not readme.exists():
        issues.append("MISSING: README.md")
    else:
        lines = readme.read_text().splitlines()
        if len(lines) < 20:
            warnings.append(f"README: only {len(lines)} lines — may not pass stranger test")

    # 11. Copyright headers in .py files
    py_files = [f for f in tracked if f.suffix == '.py']
    missing_headers = []
    for f in py_files:
        try:
            head = f.read_text()[:200]
            if "Copyright" not in head and "SPDX" not in head:
                missing_headers.append(f.name)
        except Exception:
            pass
    if missing_headers:
        warnings.append(f"COPYRIGHT: {len(missing_headers)} .py files missing headers: {', '.join(missing_headers[:5])}")

    # --- Build result ---
    if issues:
        msg = "PRE-PUBLISH AUDIT FAILED\n\n"
        msg += f"{len(issues)} blocking issue(s):\n"
        for i in issues[:15]:
            msg += f"  - {i}\n"
        if warnings:
            msg += f"\n{len(warnings)} warning(s):\n"
            for w in warnings[:10]:
                msg += f"  - {w}\n"
        msg += "\nFix these before making public."
        return {"decision": "block", "reason": msg}

    if warnings:
        msg = "PRE-PUBLISH AUDIT PASSED with warnings:\n"
        for w in warnings:
            msg += f"  - {w}\n"
        return {"decision": "allow", "reason": msg}

    return {"decision": "allow", "reason": "Pre-publish audit passed. All clear."}


def _find_repo_path() -> Path | None:
    """Try to find the repo root from cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


def _git_tracked_files(repo_path: Path) -> list[Path]:
    """Get all git-tracked files."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "ls-files", "-z"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return [repo_path / f for f in result.stdout.split('\0') if f]
    except Exception:
        pass
    return []


if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    if check(tool_name, tool_input, data):
        result = action(tool_name, tool_input, data)
        print(json.dumps(result))
    else:
        print(json.dumps({"decision": "allow"}))
