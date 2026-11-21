"""本專案實例檔內容測試（Spec-0035、Spec-0036、Spec-0037）。

驗證 `.agents/project/` 下的實例檔持有本專案的具體標準；閉環核心的結構測試位於 `.agents/tests/`。
本檔屬專案測試，移植時不隨核心帶走。只讀取版控中的規範文件，不讀取本機 data/ 或 resume/。
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / ".agents"
ARCH_CHECKLIST = AGENTS_DIR / "skills" / "feature-design" / "references" / "arch_review_checklist.md"
ARCH_CRITERIA = AGENTS_DIR / "project" / "arch_review_criteria.md"
REVIEW_CRITERIA = AGENTS_DIR / "project" / "review_criteria.md"
PROFILE = AGENTS_DIR / "project" / "profile.md"
ROW = re.compile(r"^\|\s*\**(\d)\**\s*\|(.+)\|\s*$", re.MULTILINE)
CATEGORY = re.compile(r"^### (\d)\. ", re.MULTILINE)


def _rows(text: str) -> dict:
    return {int(num): [cell.strip() for cell in rest.split("|")] for num, rest in ROW.findall(text)}


def _dimension_name(cell: str) -> str:
    return re.sub(r"\s*\(.*\)\s*$", "", cell.replace("*", "")).strip()


class TestProjectInstanceFiles(unittest.TestCase):
    def test_arch_criteria_cover_all_dimensions(self):
        """Spec-0035 AC-2：Gate 1 實例檔逐維度皆有通過標準，維度名稱與核心一致"""
        core_rows = _rows(ARCH_CHECKLIST.read_text(encoding="utf-8"))
        rows = _rows(ARCH_CRITERIA.read_text(encoding="utf-8"))
        self.assertEqual(sorted(rows), list(range(1, 9)))
        for num, cells in rows.items():
            with self.subTest(dimension=num):
                self.assertEqual(_dimension_name(cells[0]), _dimension_name(core_rows[num][0]))
                self.assertTrue(cells[1])

    def test_review_criteria_align_with_core_and_hold_quota_values(self):
        """Spec-0036 AC-2：Gate 2 實例檔類別編號與核心一致，並持有配額數值正本與圍欄標籤"""
        text = REVIEW_CRITERIA.read_text(encoding="utf-8")
        self.assertEqual([int(n) for n in CATEGORY.findall(text)], list(range(1, 10)))
        for fragment in ("25MB", "30 頁", "10x", "上限數值的文件正本", "<resume_content>", "Text-First", "80 字元"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

    def test_profile_covers_project_facts(self):
        """Spec-0037 AC-1：專案概況檔涵蓋入口、主要流程、持久化結構、敏感資料類型、測試環境"""
        text = PROFILE.read_text(encoding="utf-8")
        for heading in ("## 1. 入口與介面", "## 2. 主要流程", "## 3. 持久化結構", "## 4. 敏感資料類型", "## 5. 測試環境"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        for fact in ("convert_to_md.py", "轉檔", "檢索", "idx:resumes", "求職者姓名", "DB 15"):
            with self.subTest(fact=fact):
                self.assertIn(fact, text)


if __name__ == "__main__":
    unittest.main()
