"""
安全評估範圍 Gate 1 檢查白箱單元測試（Spec-0030 AC-1、AC-3；verify_doc_sync.py）
全部為記憶體內的虛構規格文字與暫存目錄，零網路、零 docs/ 與 data/ 讀取。
"""
import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".agents" / "skills" / "doc-sync" / "scripts" / "verify_doc_sync.py"
_spec = importlib.util.spec_from_file_location("verify_doc_sync_security", _SCRIPT)
vds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vds)

THREAT_TABLE = """
| 邊界／資料流 | STRIDE | 威脅 | 緩解措施 | 對應 NFR／測試 | 殘餘風險 |
| :--- | :---: | :--- | :--- | :--- | :--- |
| 瀏覽器 ↔ Web 服務 | **I** | 外站跨來源讀取 | 不開放跨來源許可 | NFR-1 | 無 |
"""


def make_spec(scope_line, body=""):
    return f"""# 規格
## 5. 非功能需求與威脅建模
{body}
## 6. 驗收標準
- AC-1：王小明的文件可被檢索。
{scope_line}
品質評測範圍：否
## 7. 規模
"""


def run_check(specs, enforced_from=31):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = vds.check_security_ac_specs(specs, enforced_from)
    return result, buffer.getvalue()


class TestSecurityScopeDeclaration(unittest.TestCase):
    def test_in_scope_with_threat_table_and_nfr_passes(self):
        ok, out = run_check([("0031-x.md", make_spec("安全評估範圍：是", THREAT_TABLE + "\n- NFR-1：跨來源請求不得回傳 ACAO。"))])
        self.assertTrue(ok)
        self.assertIn("宣告屬範圍之規格 1 個", out)

    def test_in_scope_without_threat_table_fails(self):
        ok, out = run_check([("0031-x.md", make_spec("安全評估範圍：是", "- NFR-1：延遲 P95 ≤ 30 s。"))])
        self.assertFalse(ok)
        self.assertIn("缺少 STRIDE 威脅表", out)
        self.assertNotIn("缺少 NFR-*", out)

    def test_in_scope_without_nfr_fails(self):
        table_without_nfr = THREAT_TABLE.replace("NFR-1", "TC-01")
        ok, out = run_check([("0031-x.md", make_spec("安全評估範圍：是", table_without_nfr))])
        self.assertFalse(ok)
        self.assertIn("缺少 NFR-*", out)
        self.assertNotIn("缺少 STRIDE 威脅表", out)

    def test_undeclared_new_spec_fails(self):
        ok, out = run_check([("0031-x.md", make_spec(""))])
        self.assertFalse(ok)
        self.assertIn("缺少「安全評估範圍：是/否」宣告", out)

    def test_out_of_scope_passes_without_table(self):
        ok, _ = run_check([("0031-x.md", make_spec("安全評估範圍：否（僅修改說明文字）"))])
        self.assertTrue(ok)

    def test_old_specs_are_not_retroactively_checked(self):
        ok, out = run_check([("0030-x.md", make_spec("")), ("0015-y.md", make_spec("安全評估範圍：是"))])
        self.assertTrue(ok)
        self.assertNotIn("FAIL", out)

    def test_boundary_at_enforcement_number(self):
        ok, _ = run_check([("0007-x.md", make_spec(""))], enforced_from=7)
        self.assertFalse(ok)

    def test_spec_without_number_is_skipped(self):
        ok, _ = run_check([("draft.md", make_spec(""))])
        self.assertTrue(ok)

    def test_acceptance_declaration_wins_over_quoted_example(self):
        body = "規則說明：範例 `安全評估範圍：是` 需附威脅表。"
        ok, _ = run_check([("0031-x.md", make_spec("安全評估範圍：否", body))])
        self.assertTrue(ok)

    def test_quality_and_security_patterns_do_not_cross_match(self):
        text = make_spec("安全評估範圍：是", THREAT_TABLE)
        self.assertTrue(vds.security_scope(text))
        self.assertFalse(vds.quality_scope(text))

    def test_stride_letter_in_prose_is_not_a_threat_table(self):
        prose = "| 名稱 | 說明 |\n| :--- | :--- |\n| Redis | Stores Index |\n- NFR-1：x"
        ok, out = run_check([("0031-x.md", make_spec("安全評估範圍：是", prose))])
        self.assertFalse(ok)
        self.assertIn("缺少 STRIDE 威脅表", out)


class TestCoreFiles(unittest.TestCase):
    def test_missing_core_file_fails_and_names_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            present = pathlib.Path("a/present.md")
            (root / present).parent.mkdir(parents=True)
            (root / present).write_text("x", encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                ok = vds.check_core_files(root, (present, pathlib.Path("b/framework.md")))
            self.assertFalse(ok)
            self.assertIn("b/framework.md", buffer.getvalue())

    def test_repository_core_files_present(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ok = vds.check_core_files()
        self.assertTrue(ok, buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
