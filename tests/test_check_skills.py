"""scripts/check_skills.py 단위 테스트.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_check_skills.py
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_skills  # noqa: E402
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


class TestMain(unittest.TestCase):
    """`main()`의 CLI 진입점(디렉터리 존재/파일 존재 검증, 종료 코드, FAIL/OK/고아 출력)을 검증한다.

    `check_skill_file`/`find_orphaned_commands`는 위에서 이미 단위 테스트했으므로, 여기서는
    main()이 그 결과를 올바른 종료 코드와 출력으로 조립하는지만 확인한다 — main() 자체는
    이전까지 CI에서 실제 skills/*.md(항상 유효)로만 간접 실행돼, 실패 경로(디렉터리 없음/
    파일 없음/검증 실패/고아 커맨드)가 회귀해도 테스트가 잡아내지 못하는 사각지대였다.
    """

    def _write(self, tmp_dir: str, name: str, content: str) -> Path:
        path = Path(tmp_dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_directory_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with mock.patch.object(check_skills, "SKILLS_DIR", missing):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_skills.main(), 1)
                self.assertIn("디렉터리를 찾을 수 없습니다", stderr.getvalue())

    def test_no_skill_files_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "README.md", "# 안내\n")  # README.md만 있으면 검증 대상 0개
            with mock.patch.object(check_skills, "SKILLS_DIR", Path(tmp)):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_skills.main(), 1)
                self.assertIn("검증할 스킬 파일이 없습니다", stderr.getvalue())

    def test_all_valid_and_synced_returns_0(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            self._write(skills_tmp, "demo-skill.md", VALID_SKILL)
            self._write(cmd_tmp, "demo-skill.md", VALID_SKILL)
            # REPO_ROOT도 함께 patch — main()이 path.relative_to(REPO_ROOT)로 출력용
            # 상대경로를 만드는데, 기본 REPO_ROOT(실제 저장소 루트)로는 임시 디렉터리
            # 경로가 subpath가 아니라 ValueError가 난다.
            with (
                mock.patch.object(check_skills, "SKILLS_DIR", Path(skills_tmp)),
                mock.patch.object(check_skills, "COMMANDS_DIR", Path(cmd_tmp)),
                mock.patch.object(check_skills, "REPO_ROOT", Path(skills_tmp)),
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(check_skills.main(), 0)
                self.assertIn("[OK]", stdout.getvalue())
                self.assertIn("모두 구조 검증 통과", stdout.getvalue())

    def test_invalid_file_returns_1(self):
        broken = "# /demo-skill\n\n프론트매터 없음.\n"
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            self._write(skills_tmp, "demo-skill.md", broken)
            with (
                mock.patch.object(check_skills, "SKILLS_DIR", Path(skills_tmp)),
                mock.patch.object(check_skills, "COMMANDS_DIR", Path(cmd_tmp)),
                mock.patch.object(check_skills, "REPO_ROOT", Path(skills_tmp)),
            ):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_skills.main(), 1)
                self.assertIn("[FAIL]", stdout.getvalue())
                self.assertIn("스킬 구조 검증 실패", stderr.getvalue())

    def test_orphaned_command_returns_1(self):
        with tempfile.TemporaryDirectory() as skills_tmp, tempfile.TemporaryDirectory() as cmd_tmp:
            self._write(skills_tmp, "demo-skill.md", VALID_SKILL)
            self._write(cmd_tmp, "demo-skill.md", VALID_SKILL)
            self._write(cmd_tmp, "renamed-away.md", "x")  # skills/renamed-away.md는 이제 없음
            with (
                mock.patch.object(check_skills, "SKILLS_DIR", Path(skills_tmp)),
                mock.patch.object(check_skills, "COMMANDS_DIR", Path(cmd_tmp)),
                mock.patch.object(check_skills, "REPO_ROOT", Path(skills_tmp)),
            ):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_skills.main(), 1)
                self.assertIn("고아 파일", stdout.getvalue())
                self.assertIn("renamed-away.md", stdout.getvalue())
                self.assertIn("스킬 구조 검증 실패", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
