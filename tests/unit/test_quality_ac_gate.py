"""
品質驗收條件 Gate 1 檢查白箱單元測試（doc-sync / verify_doc_sync.py）
全部為記憶體內的虛構規格文字，零網路、零 docs/ 與 data/ 讀取。
"""
import contextlib
import importlib.util
import io
import pathlib
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".agents" / "skills" / "doc-sync" / "scripts" / "verify_doc_sync.py"
_spec = importlib.util.spec_from_file_location("verify_doc_sync", _SCRIPT)
vds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vds)

SPEC_WITH_AC = """# 規格 A
## 1. PRD
### 1.1 背景
履歷檢索需要改善排序。
### 1.5 驗收標準 (AC)
- AC1：Recall@10 不低於 0.8。
## 2. Gate 1
"""

SPEC_WITHOUT_AC = """# 規格 B
## 1. PRD
### 1.1 背景
履歷檢索需要改善排序。
### 1.5 驗收標準 (AC)
- AC1：查詢「Kubernetes」時回傳結果不為空。
## 2. Gate 1
"""

SPEC_NOT_IN_SCOPE = """# 規格 C
## 1. PRD
### 1.5 驗收標準 (AC)
- AC1：設定檔可正常載入。
## 2. Gate 1
"""

METRIC_OUTSIDE_AC = """# 規格 D
## 1. PRD
### 1.1 背景
本功能會用 Recall@K 評估檢索。
### 1.5 驗收標準 (AC)
- AC1：查詢不回傳錯誤。
## 2. Gate 1
Recall@K 與 MRR 只出現在 Gate 1 段落中。
"""


def run_check(specs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = vds.check_quality_ac_specs(specs)
    return result, buffer.getvalue()


class TestQualityAcGate(unittest.TestCase):
    def test_new_spec_missing_quality_ac_fails(self):
        result, output = run_check([("0023-retrieval-x-spec.md", SPEC_WITHOUT_AC)])
        self.assertFalse(result)
        self.assertIn("[FAIL]", output)

    def test_new_spec_with_quality_ac_passes(self):
        result, output = run_check([("0023-retrieval-x-spec.md", SPEC_WITH_AC)])
        self.assertTrue(result)
        self.assertNotIn("[FAIL]", output)

    def test_spec_outside_scope_is_ignored(self):
        result, output = run_check([("0023-config-spec.md", SPEC_NOT_IN_SCOPE)])
        self.assertTrue(result)
        self.assertNotIn("[FAIL]", output)
        self.assertNotIn("[WARN]", output)

    def test_old_spec_missing_quality_ac_only_warns(self):
        result, output = run_check([("0022-old-spec.md", SPEC_WITHOUT_AC)])
        self.assertTrue(result)
        self.assertIn("[WARN]", output)
        self.assertNotIn("[FAIL]", output)

    def test_metric_outside_acceptance_section_does_not_count(self):
        result, output = run_check([("0023-metric-outside.md", METRIC_OUTSIDE_AC)])
        self.assertFalse(result)
        self.assertIn("[FAIL]", output)

    def test_acceptance_section_stops_at_next_level_two_heading(self):
        section = vds.extract_acceptance_section(METRIC_OUTSIDE_AC)
        self.assertIn("查詢不回傳錯誤", section)
        self.assertNotIn("Recall@K 與 MRR", section)

    def test_spec_without_number_is_treated_as_old(self):
        result, output = run_check([("untitled-spec.md", SPEC_WITHOUT_AC)])
        self.assertTrue(result)
        self.assertIn("[WARN]", output)

    def test_boundary_at_enforcement_number(self):
        result_22, _ = run_check([("0022-x.md", SPEC_WITHOUT_AC)])
        result_23, _ = run_check([("0023-x.md", SPEC_WITHOUT_AC)])
        self.assertTrue(result_22)
        self.assertFalse(result_23)


if __name__ == "__main__":
    unittest.main()
