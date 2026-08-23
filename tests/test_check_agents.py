"""scripts/check_agents.py 단위 테스트.

표준 라이브러리 unittest만 사용한다 (pytest로도 실행 가능).
실행: python -m unittest tests/test_check_agents.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

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


if __name__ == "__main__":
    unittest.main()
