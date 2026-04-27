# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""Tests for auto_skill_sync.py — stdlib unittest only."""
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import auto_skill_sync as app


# ── check() ───────────────────────────────────────────────────────────────────

class TestCheck(unittest.TestCase):
    def test_edit_skill_md_matches(self):
        self.assertTrue(app.check("Edit", {"file_path": "/Users/x/.claude/skills/md-cleanup/SKILL.md.disabled"}, {}))

    def test_write_skill_md_matches(self):
        self.assertTrue(app.check("Write", {"file_path": "/Users/x/.claude/skills/foo/SKILL.md"}, {}))

    def test_non_skill_file_ignored(self):
        self.assertFalse(app.check("Edit", {"file_path": "/Users/x/.claude/skills/foo/reference.md"}, {}))

    def test_non_edit_tool_ignored(self):
        self.assertFalse(app.check("Bash", {"file_path": "/Users/x/.claude/skills/foo/SKILL.md"}, {}))


# ── _sanitize() ───────────────────────────────────────────────────────────────

class TestSanitize(unittest.TestCase):
    def test_strips_private_home_path(self):
        result = app._sanitize("path: ~/foo")
        self.assertNotIn("~/", result)
        self.assertIn("~/foo", result)

    def test_strips_telegram_bot_path(self):
        result = app._sanitize("read ${PROJECT_ROOT:-~/your-project}/CLAUDE.md")
        self.assertNotIn("telegram-claude-bot", result)

    def test_strips_vps_ip(self):
        result = app._sanitize("<user>@<vps-ip>")
        self.assertNotIn("<vps-ip>", result)

    def test_strips_specific_memory_path(self):
        result = app._sanitize("~/.claude/projects/-Users-bernard/memory/MEMORY.md")
        self.assertNotIn("-Users-bernard", result)
        self.assertIn("*/memory/", result)

    def test_clean_content_unchanged(self):
        content = "# MD Cleanup\nAudits context sources."
        self.assertEqual(app._sanitize(content), content)


# ── _find_public() ────────────────────────────────────────────────────────────

class TestFindPublic(unittest.TestCase):
    def test_finds_matching_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "maintenance" / "md-cleanup"
            skill_dir.mkdir(parents=True)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# MD Cleanup")
            with patch.object(app, "PUBLIC_REPO", Path(tmp)):
                result = app._find_public("md-cleanup")
            self.assertEqual(result, skill_md)

    def test_returns_none_for_private_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(app, "PUBLIC_REPO", Path(tmp)):
                result = app._find_public("x-tweet")
            self.assertIsNone(result)


# ── action() ──────────────────────────────────────────────────────────────────

class TestAction(unittest.TestCase):
    def test_public_skill_copies_and_pushes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Source skill
            src_dir = Path(tmp) / "skills" / "md-cleanup"
            src_dir.mkdir(parents=True)
            src = src_dir / "SKILL.md.disabled"
            src.write_text("# MD Cleanup\npath: ~/foo")

            # Public repo
            pub_dir = Path(tmp) / "public" / "maintenance" / "md-cleanup"
            pub_dir.mkdir(parents=True)
            pub_md = pub_dir / "SKILL.md"
            pub_md.write_text("old content")

            with patch.object(app, "PUBLIC_REPO", Path(tmp) / "public"), \
                 patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                result = app.action("Edit", {"file_path": str(src)}, {})

            # Content was sanitized and written
            written = pub_md.read_text()
            self.assertNotIn("~/", written)
            self.assertIn("synced", result)

    def test_private_skill_returns_vps_reminder(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "skills" / "x-tweet"
            src_dir.mkdir(parents=True)
            src = src_dir / "SKILL.md.disabled"
            src.write_text("# x-tweet")

            with patch.object(app, "PUBLIC_REPO", Path(tmp) / "empty_public"):
                Path(tmp, "empty_public").mkdir()
                result = app.action("Edit", {"file_path": str(src)}, {})

            self.assertIn("VPS", result)

    def test_git_push_failure_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "skills" / "md-cleanup"
            src_dir.mkdir(parents=True)
            src = src_dir / "SKILL.md.disabled"
            src.write_text("# MD Cleanup")

            pub_dir = Path(tmp) / "public" / "maintenance" / "md-cleanup"
            pub_dir.mkdir(parents=True)
            (pub_dir / "SKILL.md").write_text("old")

            with patch.object(app, "PUBLIC_REPO", Path(tmp) / "public"), \
                 patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth failed")
                result = app.action("Edit", {"file_path": str(src)}, {})

            self.assertIn("failed", result)


if __name__ == "__main__":
    unittest.main()
