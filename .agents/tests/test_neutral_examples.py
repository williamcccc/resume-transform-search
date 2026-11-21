"""通用核心文件中性化守護測試。

掃描全部核心 Markdown（AGENTS.md、CLAUDE.md、GEMINI.md、.agents/**、.claude/**），確認（專屬標記所在行以外）
不出現本專案識別字或「本專案為」附註。通用技術名稱（如 Redis、LLM、429）可作舉例。

守護字詞由專案實例宣告（Spec-0041）：`project.toml` 的 `[project].identifiers`（正規式清單），
移植後改為新專案的字詞，本測試即守護新專案；「本專案為」附註屬通用規則，固定於本檔。

排除範圍（屬專案實例或另有治理程序）：
* `.agents/project/`：專案實例檔。
* `project.business_skills` 所列業務技能（`.agents/skills/` 與 `.claude/skills/` 下同名資料夾）。
* AGENTS.md「本專案紅線」小節：專案專屬整節，移植時整節改寫（Spec-0040 起通用紅線 1、6、7 納入守護）。

只讀取版控中的規範文件，不讀取本機敏感目錄。屬閉環核心自我測試，移植後仍須通過。
"""
import re
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / ".agents"
TOP_LEVEL_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
PROJECT_RED_LINE_SECTION = re.compile(r"^#### 本專案紅線.*?(?=^---$)", re.MULTILINE | re.DOTALL)
# 通用規則：核心文件不得寫「本專案為」附註（任何專案皆同）
GENERIC_PATTERNS = ("本專案為",)


def _project_section() -> dict:
    with (AGENTS_DIR / "project.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def _business_skills() -> set:
    return set(_project_section()["business_skills"])


def build_pattern(terms) -> re.Pattern:
    """以實例宣告之正規式清單加上通用規則組成守護樣式。"""
    return re.compile("|".join(f"(?:{term})" for term in (*terms, *GENERIC_PATTERNS)))


PROJECT_IDENTIFIERS = build_pattern(_project_section()["identifiers"])


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


def strip_project_red_lines(text: str) -> str:
    """以等量換行取代 AGENTS.md「本專案紅線」小節，保留行號。"""
    return PROJECT_RED_LINE_SECTION.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def find_identifiers(text: str, pattern: re.Pattern = PROJECT_IDENTIFIERS) -> list:
    """回傳 (行號, 命中字) 清單；略過專屬標記所在行。"""
    return [
        (number, pattern.search(line).group(0))
        for number, line in enumerate(text.splitlines(), 1)
        if "<!-- 專案專屬" not in line and pattern.search(line)
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
                text = strip_project_red_lines(text)
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            violations.extend(f"{rel}:{number}: {word}" for number, word in find_identifiers(text))
        self.assertEqual(violations, [])

    def test_pattern_comes_from_instance_terms(self):
        """Spec-0041 AC-1：守護字詞由實例宣告；換成新專案字詞後即守護新字詞"""
        pattern = build_pattern(["demo_widget", r"\bv9\b"])
        self.assertTrue(find_identifiers("使用 `demo_widget` 元件", pattern))
        self.assertTrue(find_identifiers("規格值 v9", pattern))
        self.assertEqual(find_identifiers("規格值 v95", pattern), [])
        self.assertTrue(find_identifiers("（本專案為 `x.py`）", build_pattern([])))
        self.assertEqual(find_identifiers("規則<!-- 專案專屬 --> demo_widget", pattern), [])
        self.assertEqual(find_identifiers("模擬資料庫客戶端（如 Redis）", build_pattern([])), [])

    def test_generic_red_lines_are_guarded(self):
        """Spec-0040：只排除本專案紅線小節，通用紅線寫回本專案附註須被抓到。"""
        pattern = build_pattern(["demo_widget"])
        doc = (
            "#### 通用紅線（任何專案適用）\n"
            "* **紅線 1**：Domain 契約檔（`layers.domain_interfaces`，本專案為 `x.py`）\n"
            "\n#### 本專案紅線（移植時整節改寫）\n"
            "* **紅線 2**：demo_widget 轉檔\n"
            "\n---\n"
        )
        stripped = strip_project_red_lines(doc)
        self.assertEqual(stripped.count("\n"), doc.count("\n"))
        self.assertEqual([word for _, word in find_identifiers(stripped, pattern)], ["本專案為"])

    def test_agents_md_project_section_keeps_red_line_values(self):
        """Spec-0040：紅線 1、6 本專案值移入本專案紅線小節，通用紅線不含附註。"""
        text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        section = PROJECT_RED_LINE_SECTION.search(text)
        self.assertIsNotNone(section)
        self.assertIn("紅線 1、6 本專案對應", section.group(0))
        self.assertNotIn("本專案為", strip_project_red_lines(text))


if __name__ == "__main__":
    unittest.main()
