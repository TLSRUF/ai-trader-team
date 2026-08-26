"""scripts/check_agents.py 단위 테스트.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_check_agents.py
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

import check_agents  # noqa: E402
from check_agents import check_agent_file  # noqa: E402

VALID_AGENT = """# 테스트 분석가 (Test Analyst)

## 담당 관점

테스트용 관점 설명.

## 핵심 질문

> 테스트 질문?

## 우선순위로 보는 데이터

1. 항목 A
2. 항목 B

## 평가 기준

| 점수 | 기준 |
|---|---|
| 5 | 최고 |

## 출력 포맷 (team-lead 보고용)

```
## 테스트 분석가 보고
- 결론 태그: Bull / Bear / Neutral
```
"""


class TestCheckAgentFile(unittest.TestCase):
    def _write(self, tmp_dir: str, name: str, content: str) -> Path:
        path = Path(tmp_dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_valid_file_has_no_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "test-analyst.md", VALID_AGENT)
            self.assertEqual(check_agent_file(path), [])

    def test_missing_role_heading(self):
        broken = VALID_AGENT.replace("## 담당 관점\n\n테스트용 관점 설명.\n\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "test-analyst.md", broken)
            errors = check_agent_file(path)
            self.assertTrue(any("담당 관점" in e for e in errors))

    def test_missing_priority_data_heading(self):
        broken = VALID_AGENT.replace(
            "## 우선순위로 보는 데이터\n\n1. 항목 A\n2. 항목 B\n\n", ""
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "test-analyst.md", broken)
            errors = check_agent_file(path)
            self.assertTrue(any("우선순위로 보는 데이터" in e for e in errors))

    def test_missing_criteria_heading(self):
        broken = VALID_AGENT.replace(
            "## 평가 기준\n\n| 점수 | 기준 |\n|---|---|\n| 5 | 최고 |\n\n", ""
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "test-analyst.md", broken)
            errors = check_agent_file(path)
            self.assertTrue(any("평가 기준" in e for e in errors))

    def test_missing_output_format_heading(self):
        broken = VALID_AGENT.split("## 출력 포맷")[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "test-analyst.md", broken)
            errors = check_agent_file(path)
            self.assertTrue(any("출력 포맷" in e for e in errors))

    def test_multiple_missing_headings_reported_together(self):
        broken = "# 테스트 분석가\n\n아무 헤딩도 없음.\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "test-analyst.md", broken)
            errors = check_agent_file(path)
            self.assertEqual(len(errors), 5)


class TestMain(unittest.TestCase):
    """`main()`의 CLI 진입점(디렉터리 존재/파일 존재 검증, 종료 코드, FAIL/OK 출력)을 검증한다.

    `check_agent_file`은 위에서 이미 단위 테스트했으므로, 여기서는 main()이 그 결과를
    올바른 종료 코드와 출력으로 조립하는지만 확인한다 — main() 자체는 이전까지
    CI에서 실제 agents/*.md(항상 유효)로만 간접 실행돼, 실패 경로(디렉터리 없음/
    파일 없음/검증 실패)가 회귀해도 테스트가 잡아내지 못하는 사각지대였다.
    """

    def _write(self, tmp_dir: str, name: str, content: str) -> Path:
        path = Path(tmp_dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_directory_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with mock.patch.object(check_agents, "AGENTS_DIR", missing):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_agents.main(), 1)
                self.assertIn("디렉터리를 찾을 수 없습니다", stderr.getvalue())

    def test_no_agent_files_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "README.md", "# 안내\n")  # README.md만 있으면 검증 대상 0개
            with mock.patch.object(check_agents, "AGENTS_DIR", Path(tmp)):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_agents.main(), 1)
                self.assertIn("검증할 에이전트 파일이 없습니다", stderr.getvalue())

    def test_all_valid_returns_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "test-analyst.md", VALID_AGENT)
            # REPO_ROOT도 함께 patch — main()이 path.relative_to(REPO_ROOT)로 출력용 상대경로를
            # 만드는데, 기본 REPO_ROOT(실제 저장소 루트)로는 임시 디렉터리 경로가 subpath가
            # 아니라 ValueError가 난다.
            with (
                mock.patch.object(check_agents, "AGENTS_DIR", Path(tmp)),
                mock.patch.object(check_agents, "REPO_ROOT", Path(tmp)),
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(check_agents.main(), 0)
                self.assertIn("[OK]", stdout.getvalue())
                self.assertIn("모두 구조 검증 통과", stdout.getvalue())

    def test_invalid_file_returns_1(self):
        broken = "# 테스트 분석가\n\n아무 헤딩도 없음.\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "test-analyst.md", broken)
            with (
                mock.patch.object(check_agents, "AGENTS_DIR", Path(tmp)),
                mock.patch.object(check_agents, "REPO_ROOT", Path(tmp)),
            ):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(check_agents.main(), 1)
                self.assertIn("[FAIL]", stdout.getvalue())
                self.assertIn("에이전트 구조 검증 실패", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
