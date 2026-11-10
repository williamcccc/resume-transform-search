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


def make_spec(scope_line, ac_lines, extra=""):
    return f"""# 規格
## 1. PRD
### 1.1 背景
履歷檢索需要改善排序。
### 1.5 驗收標準 (AC)
{scope_line}
{ac_lines}
### 1.6 非功能需求
{extra}
## 2. Gate 1
"""


IN_SCOPE_WITH_METRIC = make_spec("品質評測範圍：是", "- AC1：Recall@10 不低於 0.8。")
IN_SCOPE_WITHOUT_METRIC = make_spec("品質評測範圍：是", "- AC1：查詢「Kubernetes」時回傳結果不為空。")
OUT_OF_SCOPE = make_spec("品質評測範圍：否", "- AC1：uvicorn 可正常啟動，並支援 prompt 檢索與生成 API。")
UNDECLARED = make_spec("", "- AC1：設定檔可正常載入。")


def run_check(specs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = vds.check_quality_ac_specs(specs)
    return result, buffer.getvalue()


class TestQualityScopeDeclaration(unittest.TestCase):
    def test_new_spec_in_scope_with_metric_passes(self):
        result, output = run_check([("0023-x.md", IN_SCOPE_WITH_METRIC)])
        self.assertTrue(result)
        self.assertNotIn("[FAIL]", output)

    def test_new_spec_in_scope_without_metric_fails(self):
        result, output = run_check([("0023-x.md", IN_SCOPE_WITHOUT_METRIC)])
        self.assertFalse(result)
        self.assertIn("缺少品質指標", output)

    def test_out_of_scope_declaration_skips_even_with_keywords(self):
        result, output = run_check([("0023-x.md", OUT_OF_SCOPE)])
        self.assertTrue(result)
        self.assertNotIn("[FAIL]", output)
        self.assertNotIn("[WARN]", output)

    def test_new_spec_without_declaration_fails(self):
        result, output = run_check([("0023-x.md", UNDECLARED)])
        self.assertFalse(result)
        self.assertIn("缺少「品質評測範圍", output)

    def test_old_spec_without_declaration_is_silently_skipped(self):
        result, output = run_check([("0022-x.md", UNDECLARED)])
        self.assertTrue(result)
        self.assertNotIn("[WARN]", output)
        self.assertNotIn("[FAIL]", output)

    def test_old_spec_in_scope_without_metric_only_warns(self):
        result, output = run_check([("0022-x.md", IN_SCOPE_WITHOUT_METRIC)])
        self.assertTrue(result)
        self.assertIn("[WARN]", output)

    def test_boundary_at_enforcement_number(self):
        result_22, _ = run_check([("0022-x.md", IN_SCOPE_WITHOUT_METRIC)])
        result_23, _ = run_check([("0023-x.md", IN_SCOPE_WITHOUT_METRIC)])
        self.assertTrue(result_22)
        self.assertFalse(result_23)

    def test_spec_without_number_is_treated_as_old(self):
        result, output = run_check([("untitled-spec.md", IN_SCOPE_WITHOUT_METRIC)])
        self.assertTrue(result)
        self.assertIn("[WARN]", output)

    def test_scope_declaration_variants(self):
        self.assertTrue(vds.quality_scope("品質評測範圍: 是"))
        self.assertTrue(vds.quality_scope("**品質評測範圍**：**是**"))
        self.assertFalse(vds.quality_scope("品質評測範圍：否"))
        self.assertIsNone(vds.quality_scope("品質評測：是"))


class TestQualityMetricPattern(unittest.TestCase):
    def assert_metric(self, ac_line, expected):
        spec = make_spec("品質評測範圍：是", ac_line)
        self.assertEqual(vds.has_quality_ac(spec), expected, ac_line)

    def test_concrete_metrics_count(self):
        for line in ("- Recall@5 ≥ 0.7", "- precision@k ≥ 0.6", "- MRR ≥ 0.5", "- nDCG@10 ≥ 0.6",
                     "- 欄位F1 ≥ 0.9", "- 欄位 F1-score ≥ 0.9", "- 評審分數平均 ≥ 4", "- 評審平均分數 ≥ 4",
                     "- 人工校準一致率 ≥ 80%"):
            self.assert_metric(line, True)

    def test_vague_words_do_not_count(self):
        for line in ("- 通過 Gate 1 評審", "- 完成人工校準", "- 撰寫 rubric", "- 支援 F12 快捷鍵",
                     "- 欄位 AF1 已移除", "- 參考 MRRS 文件"):
            self.assert_metric(line, False)


class TestExtractAcceptanceSection(unittest.TestCase):
    def test_level_three_heading_stops_at_sibling_subsection(self):
        spec = make_spec("品質評測範圍：是", "- AC1：查詢不回傳錯誤。", extra="Recall@10 寫在非功能需求中。")
        section = vds.extract_acceptance_section(spec)
        self.assertIn("查詢不回傳錯誤", section)
        self.assertNotIn("Recall@10", section)
        self.assertFalse(vds.has_quality_ac(spec))

    def test_level_two_heading_includes_child_subsections(self):
        spec = "## 4. 驗收標準\n### AC1\n- MRR ≥ 0.5\n## 5. 其他\nnDCG 出現在其他段落\n"
        section = vds.extract_acceptance_section(spec)
        self.assertIn("MRR", section)
        self.assertNotIn("nDCG", section)

    def test_missing_acceptance_heading_returns_empty(self):
        spec = "# 規格\n品質評測範圍：是\nRecall@10 ≥ 0.8\n"
        self.assertEqual(vds.extract_acceptance_section(spec), "")
        self.assertFalse(vds.has_quality_ac(spec))

    def test_hash_lines_inside_code_fence_are_not_headings(self):
        spec = "## 驗收標準\n```bash\n## 這是註解不是標題\n```\n- Recall@5 ≥ 0.7\n## 下一節\n"
        self.assertIn("Recall@5", vds.extract_acceptance_section(spec))


if __name__ == "__main__":
    unittest.main()
