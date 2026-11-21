"""Gate 2 檢核清單通用化與 .agents 專案相依清理之文件結構測試（Spec-0036）；閉環核心自我測試（Spec-0037），移植後仍須通過。

只讀取版控中的規範文件，不讀取本機 data/ 或 resume/。
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / ".agents"
CHECKLIST = AGENTS_DIR / "skills" / "code-review" / "references" / "review_checklist.md"
PORTING = AGENTS_DIR / "PORTING.md"
PROJECT_TERMS = re.compile(r"Redis|Gemini|履歷|候選人|PDF|Docx|DOCX|切片|resume_content|convert_to_md|AppConfig")
CATEGORY = re.compile(r"^### (\d)\. ", re.MULTILINE)
UPGRADE_RULE_FILES = (
    AGENTS_DIR / "workflows" / "bug.md",
    AGENTS_DIR / "skills" / "bug-triage" / "SKILL.md",
    AGENTS_DIR / "skills" / "bug-triage" / "references" / "bug_report_template.md",
    PROJECT_ROOT / "docs" / "templates" / "bug_report_template.md",
)


class TestReviewChecklistPortable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CHECKLIST.read_text(encoding="utf-8")

    def test_core_checklist_free_of_markers_and_project_terms(self):
        """AC-1：核心清單無專屬標記，亦無本專案元件名稱"""
        self.assertNotIn("<!-- 專案專屬", self.core)
        self.assertEqual(PROJECT_TERMS.findall(self.core), [])

    def test_core_keeps_nine_categories_and_severity_definitions(self):
        """AC-1：核心清單保留 9 類結構與嚴重等級定義"""
        self.assertEqual([int(n) for n in CATEGORY.findall(self.core)], list(range(1, 10)))
        for level in ("[P0 阻斷型缺陷", "[P1 重大防護缺陷", "[P2 品質與風格缺陷"):
            self.assertIn(level, self.core)

    def test_upgrade_rule_uses_config_module_everywhere(self):
        """AC-3：升級條件 3 在 4 個檔案一致改為 config.module"""
        for path in UPGRADE_RULE_FILES:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("設定模組（`config.module`）新增環境變數", text)
                self.assertNotIn("`AppConfig` 環境變數", text)

    def test_doc_sync_and_qa_testing_free_of_project_terms(self):
        """AC-3：doc_sync_checklist 與 qa-testing 技能不含本專案元件名稱"""
        for path in (
            AGENTS_DIR / "skills" / "doc-sync" / "references" / "doc_sync_checklist.md",
            AGENTS_DIR / "skills" / "qa-testing" / "SKILL.md",
        ):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(re.findall(r"IVectorStore|IEmbeddingService|Redis|Gemini|候選人|PDF", text), [])

    def test_porting_declares_python_scope_and_lists_instance_files(self):
        """AC-4：PORTING.md 宣告 Python 適用範圍並列出兩份實例檔（舉例中性化後已無「選擇性中性化」步驟）"""
        text = PORTING.read_text(encoding="utf-8")
        self.assertIn("**適用範圍**", text)
        self.assertIn("Python 專案", text)
        self.assertNotIn("中性化舉例", text)
        for name in ("arch_review_criteria.md", "review_criteria.md"):
            with self.subTest(name=name):
                self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
