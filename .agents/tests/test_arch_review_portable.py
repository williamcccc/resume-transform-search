"""架構前審 8 大維度通用化之文件結構測試（Spec-0035）；閉環核心自我測試（Spec-0037），移植後仍須通過。

只讀取版控中的規範文件，不讀取本機敏感目錄（`privacy.sensitive_dirs`）。
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = PROJECT_ROOT / ".agents" / "skills" / "feature-design" / "references" / "arch_review_checklist.md"
ADR_TEMPLATE = PROJECT_ROOT / ".agents" / "skills" / "doc-sync" / "references" / "adr_template.md"
ROW = re.compile(r"^\|\s*\**(\d)\**\s*\|(.+)\|\s*$", re.MULTILINE)


def _rows(text: str) -> dict:
    """回傳 {維度編號: [欄位文字...]}，欄位已去除前後空白。"""
    return {int(num): [cell.strip() for cell in rest.split("|")] for num, rest in ROW.findall(text)}


def _dimension_name(cell: str) -> str:
    """取維度中文名稱（去除粗體與括號內英文）。"""
    return re.sub(r"\s*\(.*\)\s*$", "", cell.replace("*", "")).strip()


class TestArchReviewPortable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CHECKLIST.read_text(encoding="utf-8")
        cls.adr = ADR_TEMPLATE.read_text(encoding="utf-8")

    def test_core_checklist_has_no_project_markers(self):
        """AC-1：核心清單不含專案專屬標記"""
        self.assertNotIn("<!-- 專案專屬", self.core)

    def test_core_dimensions_complete_with_condition_question_standard(self):
        """AC-1：8 個維度皆有名稱、適用條件、要問的問題與對應標準"""
        rows = _rows(self.core)
        self.assertEqual(sorted(rows), list(range(1, 9)))
        for num, cells in rows.items():
            with self.subTest(dimension=num):
                self.assertEqual(len(cells), 4)
                self.assertTrue(all(cells), f"維度 {num} 有空白欄位")

    def test_adr_template_dimension_names_match_core(self):
        """AC-3：ADR 範本第 5 節維度名稱與核心一致，且無專屬標記"""
        section = self.adr.split("## 5.", 1)[1].split("\n## ", 1)[0]
        core_rows = _rows(self.core)
        rows = _rows(section)
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertNotIn("<!-- 專案專屬", section)
        for num, cells in rows.items():
            with self.subTest(dimension=num):
                self.assertEqual(_dimension_name(cells[0]), _dimension_name(core_rows[num][0]))


if __name__ == "__main__":
    unittest.main()
