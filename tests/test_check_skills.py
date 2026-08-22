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

from check_skills import _parse_frontmatter, check_skill_file  # noqa: E402

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

    def test_valid_file_has_no_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "demo-skill.md", VALID_SKILL)
            self.assertEqual(check_skill_file(path), [])

    def test_missing_frontmatter_entirely(self):
        broken = "# /demo-skill\n\n본문만 있음.\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "demo-skill.md", broken)
            errors = check_skill_file(path)
            self.assertTrue(any("프론트매터" in e for e in errors))

    def test_missing_argument_hint_key(self):
        broken = VALID_SKILL.replace("argument-hint: <티커>\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "demo-skill.md", broken)
            errors = check_skill_file(path)
            self.assertTrue(any("argument-hint" in e for e in errors))

    def test_missing_heading(self):
        broken = VALID_SKILL.replace("# /demo-skill\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "demo-skill.md", broken)
            errors = check_skill_file(path)
            self.assertTrue(any("헤딩" in e for e in errors))

    def test_heading_must_match_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "other-name.md", VALID_SKILL)
            errors = check_skill_file(path)
            self.assertTrue(any("other-name" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
