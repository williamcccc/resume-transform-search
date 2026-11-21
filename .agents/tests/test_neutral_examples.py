"""通用核心文件中性化守護測試。

掃描全部核心 Markdown（AGENTS.md、CLAUDE.md、GEMINI.md、.agents/**、.claude/**），確認（專屬標記所在行以外）
不出現本專案識別字或「本專案為」附註，亦不連結或引用本專案規格歷史（Spec-0042；移植只複製核心，歷史不隨行）。
通用技術名稱（如 Redis、LLM、429）可作舉例。
核心 Python（Spec-0042）：`.agents/lib/` 與核心技能 `scripts/` 全文、`.agents/tests/` 模組 docstring 不得出現本專案識別字
（測試夾具需操作路徑字串，不納入）。

守護字詞由專案實例宣告（Spec-0041）：`project.toml` 的 `[project].identifiers`（正規式清單），
移植後改為新專案的字詞，本測試即守護新專案；「本專案為」附註屬通用規則，固定於本檔。

排除範圍（屬專案實例或另有治理程序）：
* `.agents/project/`：專案實例檔。
* `project.business_skills` 所列業務技能（`.agents/skills/` 與 `.claude/skills/` 下同名資料夾）。
* AGENTS.md「本專案紅線」小節：專案專屬整節，移植時整節改寫（Spec-0040 起通用紅線 1、6、7 納入守護）。

只讀取版控中的規範文件，不讀取本機敏感目錄。屬閉環核心自我測試，移植後仍須通過。
"""
import ast
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
# 通用規則：核心文件不得連結本專案規格歷史或引用其編號（Spec-0042）
HISTORY_REFERENCE = re.compile(r"\]\([^)]*docs/(?:specs|qa_reports|adr|bugs)/\d|\b(?:Spec|ADR|QA|Bug)-\d{4}\b")


def _project_section() -> dict:
    with (AGENTS_DIR / "project.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def _business_skills() -> set:
    return set(_project_section()["business_skills"])


def build_pattern(terms) -> re.Pattern:
    """以實例宣告之正規式清單加上通用規則組成守護樣式。"""
    return re.compile("|".join(f"(?:{term})" for term in (*terms, *GENERIC_PATTERNS)))


PROJECT_IDENTIFIERS = build_pattern(_project_section()["identifiers"])
IDENTIFIERS_ONLY = re.compile("|".join(f"(?:{t})" for t in _project_section()["identifiers"]) or r"(?!)")


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


def core_python_texts() -> list:
    """回傳 (相對路徑, 待檢文字)：程式庫與核心技能腳本為全文，閉環自我測試只取模組 docstring。"""
    skills = _business_skills()
    items = [(p, p.read_text(encoding="utf-8")) for p in sorted((AGENTS_DIR / "lib").rglob("*.py"))]
    for path in sorted((AGENTS_DIR / "skills").glob("*/scripts/**/*.py")):
        if path.relative_to(AGENTS_DIR / "skills").parts[0] not in skills:
            items.append((path, path.read_text(encoding="utf-8")))
    for path in sorted((AGENTS_DIR / "tests").rglob("*.py")):
        items.append((path, ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""))
    return [(p.relative_to(PROJECT_ROOT).as_posix(), text) for p, text in items if "__pycache__" not in p.parts]


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

    def test_core_markdown_has_no_history_references(self):
        """Spec-0042 AC-1：核心 Markdown 不連結本專案規格歷史、不引用其編號"""
        violations = []
        for path in core_markdown_files():
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            violations.extend(f"{rel}:{n}: {w}" for n, w in find_identifiers(path.read_text(encoding="utf-8"), HISTORY_REFERENCE))
        self.assertEqual(violations, [])

    def test_history_reference_pattern(self):
        self.assertTrue(find_identifiers("（[Spec-0028](../docs/specs/0028-x.md)）", HISTORY_REFERENCE))
        self.assertTrue(find_identifiers("見 [報告](../../docs/qa_reports/0030-x.md)", HISTORY_REFERENCE))
        self.assertTrue(find_identifiers("自動檢查（ADR-0037）", HISTORY_REFERENCE))
        self.assertEqual(find_identifiers("寫入 `docs/specs/XXXX-*.md`", HISTORY_REFERENCE), [])
        self.assertEqual(find_identifiers("索引 [docs/README.md](docs/README.md)", HISTORY_REFERENCE), [])

    def test_core_python_has_no_project_identifiers(self):
        """Spec-0042 AC-3：核心腳本、程式庫全文與自我測試 docstring 不含本專案識別字"""
        files = {rel for rel, _ in core_python_texts()}
        self.assertIn(".agents/skills/code-review/scripts/audit_guardrails.py", files)
        self.assertIn(".agents/lib/project_config.py", files)
        for skill in _business_skills():
            self.assertFalse([f for f in files if f"/skills/{skill}/" in f])
        violations = []
        for rel, text in core_python_texts():
            violations.extend(f"{rel}:{n}: {w}" for n, w in find_identifiers(text, IDENTIFIERS_ONLY))
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

    def test_agents_md_has_project_section_and_no_annotations_outside(self):
        """Spec-0040、Spec-0046：AGENTS.md 有本專案紅線小節，其外無「本專案為」附註（小節內容屬專案實例，不在核心驗證）。"""
        text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIsNotNone(PROJECT_RED_LINE_SECTION.search(text))
        self.assertNotIn("本專案為", strip_project_red_lines(text))


if __name__ == "__main__":
    unittest.main()
