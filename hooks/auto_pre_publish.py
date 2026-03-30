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
    repo_path = _find_repo_path(cmd)
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
        # Skip IP checks in test files — they intentionally contain fake IPs as fixtures
        is_test_file = f.name.startswith("test_") or "_test.py" in f.name or "/tests/" in str(f)
        for pattern, desc in secret_patterns:
            if desc == "Hardcoded IP address" and is_test_file:
                continue
            matches = re.findall(pattern, content)
            for match in matches:
                # Skip common false positives
                if desc == "Hardcoded IP address":
                    # Skip loopback, broadcast, and private range starts (used in SSRF blockers)
                    if match in ("0.0.0.0", "127.0.0.1", "255.255.255.255", "192.168.0.1") or \
                       match.startswith(("10.0.", "10.255.", "127.0.", "172.16.", "172.31.", "192.168.", "169.254.", "224.0.")):
                        continue
                    # Skip browser version numbers (e.g. Chrome/131.0.0.0 in User-Agent strings)
                    if match.endswith(".0.0.0"):
                        continue
                # Skip regex patterns (contain .*, \s, \b, etc.) — these are detection code, not secrets
                if any(c in match for c in (".*", "\\s", "\\b", "\\d", "[", "+")):
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
    # Extract GitHub repo name from the command (may differ from local dir name)
    gh_match = re.search(r'nardovibecoding/([a-zA-Z0-9_-]+)', cmd)
    gh_repo_name = gh_match.group(1) if gh_match else repo_path.name
    try:
        r = subprocess.run(
            ["gh", "repo", "view", f"nardovibecoding/{gh_repo_name}", "--json", "description,repositoryTopics"],
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

    # --- README quality checks (block) ---

    # 10. README exists, has substance, and key sections
    readme = repo_path / "README.md"
    if not readme.exists():
        issues.append("MISSING: README.md")
    else:
        readme_text = readme.read_text()
        readme_lines = readme_text.splitlines()
        readme_lower = readme_text.lower()

        if len(readme_lines) < 20:
            issues.append(f"README: only {len(readme_lines)} lines — won't pass stranger test")

        # Must have install/usage section
        if not re.search(r'##\s*(install|setup|getting started|quick start)', readme_lower):
            issues.append("README: no install/setup section — strangers won't know how to use it")

        # Must have description in first 10 lines (what does it do?)
        first_10 = "\n".join(readme_lines[:10])
        if len(first_10.strip()) < 50:
            issues.append("README: first 10 lines too thin — needs a clear one-line description")

        # Should have code examples
        if "```" not in readme_text:
            warnings.append("README: no code blocks — add usage examples")

        # Should have a license section or badge
        if "license" not in readme_lower:
            warnings.append("README: no license mention — add badge or section")

    # --- MEDIUM checks (block) ---

    # 10b. NOTICE repo name matches actual repo name
    notice_file = repo_path / "NOTICE"
    if notice_file.exists():
        notice_text = notice_file.read_text()
        notice_first_line = notice_text.strip().splitlines()[0] if notice_text.strip() else ""
        if notice_first_line and notice_first_line != gh_repo_name:
            issues.append(f"NOTICE: first line says '{notice_first_line}' but repo is '{gh_repo_name}'")

    # 10c. .gitignore covers .env specifically
    gitignore = repo_path / ".gitignore"
    if gitignore.exists():
        gi_text = gitignore.read_text()
        if ".env" not in gi_text:
            issues.append("GITIGNORE: .env not covered — risk of secret leaks")

    # 10d. Demo file referenced in README actually exists
    if readme.exists() and readme_text:
        demo_refs = re.findall(r'src="(demo[^"]*)"', readme_text)
        for ref in demo_refs:
            if not (repo_path / ref).exists():
                issues.append(f"README: references '{ref}' but file doesn't exist")

    # --- LOW checks (warn) ---

    # 11. No large binaries (>1MB)
    for f in tracked:
        try:
            if f.stat().st_size > 1_000_000:
                warnings.append(f"LARGE: {f.name} ({f.stat().st_size // 1024}KB)")
        except Exception:
            pass

    # 12. Copyright headers in .py and .js files
    code_files = [f for f in tracked if f.suffix in ('.py', '.js')]
    missing_headers = []
    for f in code_files:
        try:
            head = f.read_text()[:300]
            if "Copyright" not in head and "SPDX" not in head and "license" not in head.lower():
                missing_headers.append(f.name)
        except Exception:
            pass
    if missing_headers:
        warnings.append(f"COPYRIGHT: {len(missing_headers)} files missing headers: {', '.join(missing_headers[:5])}")

    # 13. Demo GIF or screenshot in README
    if readme.exists():
        if not re.search(r'\.(gif|mp4|png|jpg|jpeg|webp)', readme_text, re.IGNORECASE):
            warnings.append("README: no demo GIF or screenshot — visual demos boost adoption")

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


def _find_repo_path(cmd: str = "") -> Path | None:
    """Find repo path from the gh command or cwd."""
    # Try to extract repo name from gh command: gh repo edit nardovibecoding/REPO ...
    if cmd:
        match = re.search(r'nardovibecoding/([a-zA-Z0-9_-]+)', cmd)
        if match:
            repo_name = match.group(1)
            # Check common local paths
            for candidate in [
                Path.home() / repo_name,
                Path.home() / repo_name.replace("-", "_"),
            ]:
                if candidate.exists() and (candidate / ".git").exists():
                    return candidate
    # Fallback: git rev-parse from cwd
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
