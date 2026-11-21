"""
需求澄清與假設清單 Gate 1 檢查白箱單元測試（Spec-0049 AC-3；verify_doc_sync.py）
全部為記憶體內的虛構規格文字，零網路、零讀取 docs/ 與本機敏感目錄（`privacy.sensitive_dirs`）。
"""
import contextlib
import importlib.util
import io
import pathlib
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".agents" / "skills" / "doc-sync" / "scripts" / "verify_doc_sync.py"
_spec = importlib.util.spec_from_file_location("verify_doc_sync_assumptions", _SCRIPT)
vds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vds)

HEADER = "| # | 假設 | 來源 | 依據 |\n| :---: | :--- | :--- | :--- |\n"


def make_spec(section="", heading="## 6. 假設清單 (Assumptions)"):
    return f"""# 規格
## 5. 驗收標準
- AC-1：王小明的文件可被檢索。
品質評測範圍：否
安全評估範圍：否
{heading}
{section}
## 7. 附錄
| # | 項目 | 來源 |
| :---: | :--- | :--- |
| 1 | 其他表格 | 推測 |
"""


def valid_section(rows=None, declaration="需求澄清：已執行（共 2 題）"):
    rows = rows if rows is not None else ["| A-1 | 預設筆數維持現值 | 程式碼 | `app/x.py:3` |"]
    return f"{declaration}\n\n{HEADER}" + "\n".join(rows) + "\n"


def run_check(specs, enforced_from=49):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = vds.check_assumption_specs(specs, enforced_from)
    return result, buffer.getvalue()


class TestAssumptionList(unittest.TestCase):
    def test_valid_list_passes(self):
        ok, out = run_check([("0049-x.md", make_spec(valid_section()))])
        self.assertTrue(ok, out)
        self.assertIn("受檢規格 1 個", out)

    def test_all_five_sources_and_bold_pass(self):
        rows = [f"| A-{i} | 假設 {i} | {src} | 依據 |" for i, src in enumerate(vds.ASSUMPTION_SOURCES, 1)]
        rows.append("| A-9 | 加粗來源 | **使用者確認** | 第 1 題 |")
        ok, out = run_check([("0049-x.md", make_spec(valid_section(rows)))])
        self.assertTrue(ok, out)

    def test_skipped_declaration_passes(self):
        ok, out = run_check([("0049-x.md", make_spec(valid_section(declaration="需求澄清：略過（未命中觸發條件）")))])
        self.assertTrue(ok, out)

    def test_missing_section_fails(self):
        ok, out = run_check([("0049-x.md", make_spec(heading="## 6. 其他"))])
        self.assertFalse(ok)
        self.assertIn("缺少「假設清單」章節", out)

    def test_missing_declaration_fails(self):
        ok, out = run_check([("0049-x.md", make_spec(valid_section(declaration="")))])
        self.assertFalse(ok)
        self.assertIn("需求澄清", out)

    def test_missing_source_column_fails(self):
        section = "需求澄清：略過\n\n| # | 假設 | 依據 |\n| :---: | :--- | :--- |\n| A-1 | 某假設 | 某處 |\n"
        ok, out = run_check([("0049-x.md", make_spec(section))])
        self.assertFalse(ok)
        self.assertIn("缺少含「來源」欄之表格", out)

    def test_empty_table_fails(self):
        ok, out = run_check([("0049-x.md", make_spec(valid_section(rows=[])))])
        self.assertFalse(ok)
        self.assertIn("無資料列", out)

    def test_guess_source_fails(self):
        rows = ["| A-1 | 門檻 0.8 | 推測 | 無 |"]
        ok, out = run_check([("0049-x.md", make_spec(valid_section(rows)))])
        self.assertFalse(ok)
        self.assertIn("「推測」不合法", out)

    def test_blank_source_fails(self):
        rows = ["| A-1 | 門檻 0.8 |  | 無 |"]
        ok, out = run_check([("0049-x.md", make_spec(valid_section(rows)))])
        self.assertFalse(ok)
        self.assertIn("（空白）", out)

    def test_table_outside_section_not_counted(self):
        """第 7 節之「推測」不影響；僅檢查假設清單章節內之表格"""
        ok, _ = run_check([("0049-x.md", make_spec(valid_section()))])
        self.assertTrue(ok)

    def test_older_specs_skipped(self):
        ok, out = run_check([("0048-x.md", "# 舊規格，無假設清單\n")])
        self.assertTrue(ok)
        self.assertIn("受檢規格 0 個", out)

    def test_heading_inside_code_fence_ignored(self):
        fenced = "```markdown\n## 6. 假設清單\n需求澄清：略過\n```\n"
        ok, out = run_check([("0049-x.md", "# 規格\n## 1. 範本示例\n" + fenced)])
        self.assertFalse(ok)
        self.assertIn("缺少「假設清單」章節", out)


if __name__ == "__main__":
    unittest.main()
