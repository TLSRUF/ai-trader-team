"""scripts/check_skills.py 단위 테스트.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_check_skills.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_skills import _parse_frontmatter, check_skill_file, find_orphaned_commands  # noqa: E402

VALID_SKILL = """---
description: 테스트용 설명
argument-hint: <티커>
---

# /demo-skill

본문 내용.
"""


class TestParseFrontmatter(unittest.TestCase):
    def test_valid_frontmatter(self):
        fm = _parse_frontmatter(VALID_SKILL)
        self.assertEqual(fm["description"], "테스트용 설명")
        self.assertEqual(fm["argument-hint"], "<티커>")

    def test_missing_start_marker(self):
        self.assertIsNone(_parse_frontmatter("# /demo-skill\n본문\n"))

    def test_unclosed_frontmatter_returns_none(self):
        text = "---\ndescription: x\n\n# /demo\n"
        self.assertIsNone(_parse_frontmatter(text))

    def test_empty_text(self):
        self.assertIsNone(_parse_frontmatter(""))


class TestCheckSkillFile(unittest.TestCase):
    def _write(self, tmp_dir: str, name: str, content: str) -> Path:
        path = Path(tmp_dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def _write_synced(self, skills_tmp: str, commands_tmp: str, name: str, content: str) -> tuple[Path, Path]:
        """skills/와 .claude/commands/ 양쪽에 동일한 내용으로 파일을 만든다 (드리프트 없음)."""
        path = self._write(skills_tmp, name, content)
        self._write(commands_tmp, name, content)
        return path, Path(commands_tmp)

    def test_valid_file_has_no_errors(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path, commands_dir = self._write_synced(skills_tmp, cmd_tmp, "demo-skill.md", VALID_SKILL)
            self.assertEqual(check_skill_file(path, commands_dir), [])

    def test_missing_frontmatter_entirely(self):
        broken = "# /demo-skill\n\n본문만 있음.\n"
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path, commands_dir = self._write_synced(skills_tmp, cmd_tmp, "demo-skill.md", broken)
            errors = check_skill_file(path, commands_dir)
            self.assertTrue(any("프론트매터" in e for e in errors))

    def test_missing_argument_hint_key(self):
        broken = VALID_SKILL.replace("argument-hint: <티커>\n", "")
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path, commands_dir = self._write_synced(skills_tmp, cmd_tmp, "demo-skill.md", broken)
            errors = check_skill_file(path, commands_dir)
            self.assertTrue(any("argument-hint" in e for e in errors))

    def test_missing_heading(self):
        broken = VALID_SKILL.replace("# /demo-skill\n", "")
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path, commands_dir = self._write_synced(skills_tmp, cmd_tmp, "demo-skill.md", broken)
            errors = check_skill_file(path, commands_dir)
            self.assertTrue(any("헤딩" in e for e in errors))

    def test_heading_must_match_filename(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path, commands_dir = self._write_synced(skills_tmp, cmd_tmp, "other-name.md", VALID_SKILL)
            errors = check_skill_file(path, commands_dir)
            self.assertTrue(any("other-name" in e for e in errors))


class TestCommandSync(unittest.TestCase):
    def _write(self, tmp_dir: str, name: str, content: str) -> Path:
        path = Path(tmp_dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_command_file_is_error(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path = self._write(skills_tmp, "demo-skill.md", VALID_SKILL)
            errors = check_skill_file(path, Path(cmd_tmp))  # commands 쪽엔 아무것도 안 씀
            self.assertTrue(any("없음" in e for e in errors))

    def test_drifted_command_file_is_error(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path = self._write(skills_tmp, "demo-skill.md", VALID_SKILL)
            self._write(cmd_tmp, "demo-skill.md", VALID_SKILL + "\n오래된 내용\n")
            errors = check_skill_file(path, Path(cmd_tmp))
            self.assertTrue(any("드리프트" in e for e in errors))

    def test_synced_command_file_has_no_sync_error(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            path = self._write(skills_tmp, "demo-skill.md", VALID_SKILL)
            self._write(cmd_tmp, "demo-skill.md", VALID_SKILL)
            errors = check_skill_file(path, Path(cmd_tmp))
            self.assertEqual(errors, [])


class TestFindOrphanedCommands(unittest.TestCase):
    def _write(self, tmp_dir: str, name: str, content: str = "x") -> Path:
        path = Path(tmp_dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_no_orphans_when_fully_synced(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            skill_files = [self._write(skills_tmp, "demo-skill.md")]
            self._write(cmd_tmp, "demo-skill.md")
            self.assertEqual(find_orphaned_commands(skill_files, Path(cmd_tmp)), [])

    def test_detects_orphaned_command_file(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            skill_files = [self._write(skills_tmp, "demo-skill.md")]
            self._write(cmd_tmp, "demo-skill.md")
            self._write(cmd_tmp, "renamed-away.md")  # skills/renamed-away.md는 이제 없음
            self.assertEqual(find_orphaned_commands(skill_files, Path(cmd_tmp)), ["renamed-away.md"])

    def test_readme_is_never_flagged_as_orphan(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            skill_files = [self._write(skills_tmp, "demo-skill.md")]
            self._write(cmd_tmp, "demo-skill.md")
            self._write(cmd_tmp, "README.md")
            self.assertEqual(find_orphaned_commands(skill_files, Path(cmd_tmp)), [])

    def test_missing_commands_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as skills_tmp:
            skill_files = [self._write(skills_tmp, "demo-skill.md")]
            missing_dir = Path(skills_tmp) / "does-not-exist"
            self.assertEqual(find_orphaned_commands(skill_files, missing_dir), [])


if __name__ == "__main__":
    unittest.main()
