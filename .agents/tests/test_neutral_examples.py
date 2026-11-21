"""通用核心文件中性化守護測試。

掃描全部核心 Markdown（AGENTS.md、CLAUDE.md、GEMINI.md、.agents/**、.claude/**），確認（專屬標記所在行以外）
不再出現原專案識別字或「本專案為」附註。通用技術名稱（如 Redis、LLM、429）可作舉例。

排除範圍（屬專案實例或另有治理程序）：
* `.agents/project/`：專案實例檔。
* `project.business_skills` 所列業務技能（`.agents/skills/` 與 `.claude/skills/` 下同名資料夾）。
* AGENTS.md「核心不可變紅線」小節：紅線文字之修改屬大改並須 ADR，不由本測試約束。

只讀取版控中的規範文件，不讀取本機 data/ 或 resume/。屬閉環核心自我測試，移植後仍須通過。
"""
import re
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / ".agents"
TOP_LEVEL_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
RED_LINE_SECTION = re.compile(r"^### 核心不可變紅線\n.*?(?=^---$)", re.MULTILINE | re.DOTALL)
# 原專案識別字：業務名詞、本專案檔名／類別名／索引名與規格值，以及「本專案為」附註
PROJECT_IDENTIFIERS = re.compile(
    r"履歷|候選人|求職|招募|resume|Resume|convert_to_md|index_to_redis|search_resumes|"
    r"GeminiJudgeService|RedisVectorStore|IVectorStore|IQualityValidator|IEmbeddingService|ResumeChunk|"
    r"idx:resumes|_escape_redis_tag|src\.domain|\b768\b|(?<!功能)切片|PyMuPDF|pymupdf|本專案為"
)


def _business_skills() -> set:
    with (AGENTS_DIR / "project.toml").open("rb") as handle:
        return set(tomllib.load(handle)["project"]["business_skills"])


def core_markdown_files() -> list:
    skills = _business_skills()
    files = [PROJECT_ROOT / name for name in TOP_LEVEL_DOCS if (PROJECT_ROOT / name).is_file()]
    for base in (AGENTS_DIR, PROJECT_ROOT / ".claude"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            parts = path.relative_to(base).parts
            if parts[0] == "project" and base == AGENTS_DIR:
                continue
            if len(parts) > 1 and parts[0] == "skills" and parts[1] in skills:
                continue
            files.append(path)
    return files


def find_identifiers(text: str) -> list:
    """回傳 (行號, 命中字) 清單；略過專屬標記所在行。"""
    return [
        (number, PROJECT_IDENTIFIERS.search(line).group(0))
        for number, line in enumerate(text.splitlines(), 1)
        if "<!-- 專案專屬" not in line and PROJECT_IDENTIFIERS.search(line)
    ]


class TestNeutralExamples(unittest.TestCase):
    def test_scope_covers_core_and_excludes_instances(self):
        files = {p.relative_to(PROJECT_ROOT).as_posix() for p in core_markdown_files()}
        self.assertIn("AGENTS.md", files)
        self.assertIn(".agents/PORTING.md", files)
        self.assertIn(".agents/skills/doc-sync/SKILL.md", files)
        self.assertFalse([f for f in files if f.startswith(".agents/project/")])
        for skill in _business_skills():
            self.assertFalse([f for f in files if f"/skills/{skill}/" in f])

    def test_core_markdown_has_no_project_identifiers(self):
        violations = []
        for path in core_markdown_files():
            text = path.read_text(encoding="utf-8")
            if path.name == "AGENTS.md" and path.parent == PROJECT_ROOT:
                # 保留行號：以等量換行取代紅線小節
                text = RED_LINE_SECTION.sub(lambda m: "\n" * m.group(0).count("\n"), text)
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            violations.extend(f"{rel}:{number}: {word}" for number, word in find_identifiers(text))
        self.assertEqual(violations, [])

    def test_identifier_pattern_catches_known_residues(self):
        samples = ["（本專案為 `src/domain/interfaces.py`）", "如 `ResumeChunk`", "不得含真實履歷", "向量切片"]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(find_identifiers(sample))
        self.assertEqual(find_identifiers("規則<!-- 專案專屬 --> 履歷"), [])
        self.assertEqual(find_identifiers("模擬資料庫客戶端（如 Redis）"), [])


if __name__ == "__main__":
    unittest.main()
