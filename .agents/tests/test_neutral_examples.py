"""規範檔舉例中性化守護測試。

原列於 PORTING.md「選擇性中性化舉例」的 14 個檔案已改為通用舉例；本測試確保其中
（專屬標記所在行以外）不再出現本專案識別字。通用技術名稱（如 Redis、LLM、429）可作舉例。
只讀取版控中的規範文件，不讀取本機 data/ 或 resume/。
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / ".agents"
NEUTRAL_FILES = (
    "skills/code-review/SKILL.md",
    "skills/auto-fix/SKILL.md",
    "skills/unit-testing/SKILL.md",
    "skills/feature-design/SKILL.md",
    "developer/AGENT.md",
    "skills/auto-fix/references/rca_guide.md",
    "skills/auto-fix/references/fix_anti_patterns.md",
    "skills/unit-testing/references/mocking_patterns.md",
    "skills/unit-testing/references/unit_test_checklist.md",
    "skills/feature-design/references/prd_template.md",
    "skills/feature-design/references/tech_spec_template.md",
    "skills/qa-testing/references/test_case_template.md",
    "skills/qa-testing/references/qa_report_template.md",
    "skills/bug-triage/references/bug_report_template.md",
)
# 本專案識別字：業務名詞、本專案檔名／類別名／索引名與規格值
PROJECT_IDENTIFIERS = re.compile(
    r"履歷|候選人|求職|招募|resume|Resume|convert_to_md|index_to_redis|search_resumes|"
    r"GeminiJudgeService|RedisVectorStore|IVectorStore|IQualityValidator|ResumeChunk|"
    r"idx:resumes|_escape_redis_tag|src\.domain|\b768\b|切片|PyMuPDF|pymupdf"
)


class TestNeutralExamples(unittest.TestCase):
    def test_listed_files_have_no_project_identifiers_outside_marked_lines(self):
        for rel in NEUTRAL_FILES:
            with self.subTest(file=rel):
                lines = (AGENTS_DIR / rel).read_text(encoding="utf-8").splitlines()
                hits = [
                    f"{number}: {PROJECT_IDENTIFIERS.search(line).group(0)}"
                    for number, line in enumerate(lines, 1)
                    if "<!-- 專案專屬" not in line and PROJECT_IDENTIFIERS.search(line)
                ]
                self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
