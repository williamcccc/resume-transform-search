"""
流程分軌文件檢查白箱單元測試（Spec-0025 / verify_doc_sync.py）
涵蓋：分流表 ↔ 流程檔一致性、docs/bugs/ 檔名與索引、缺陷報告品質範圍宣告、範本鏡像一致性。
檢查邏輯一律以暫存目錄或記憶體建構虛構內容驗證；僅兩項守門測試讀取專案內的範本（缺陷報告範本、docs/templates/ 檔名清單），零網路、零讀取 data/ 與 resume/。
"""
import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".agents" / "skills" / "doc-sync" / "scripts" / "verify_doc_sync.py"
_spec = importlib.util.spec_from_file_location("verify_doc_sync_tracks", _SCRIPT)
vds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vds)


def _quiet(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


ROUTING_TABLE = """## 2. 分流
| 請求類型 | 流程檔 |
| :--- | :--- |
| 功能開發 | [feature.md](.agents/workflows/feature.md) |
| 缺陷修正 | [bug.md](.agents/workflows/bug.md) |
| 緊急止血 | [hotfix.md](./.agents/workflows/hotfix.md#適用) |
"""


class _TempRootCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, rel, content="# 內容\n"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class TestWorkflowRouting(_TempRootCase):
    def _write_three_workflows(self):
        for name in ("feature", "bug", "hotfix"):
            self._write(f".agents/workflows/{name}.md")

    def test_all_links_resolve_and_no_orphans_passes(self):
        self._write_three_workflows()
        result, output = _quiet(vds.check_workflow_routing, ROUTING_TABLE, self.root)
        self.assertTrue(result)
        self.assertIn("一致 (3 個)", output)

    def test_link_to_missing_workflow_fails(self):
        self._write(".agents/workflows/feature.md")
        self._write(".agents/workflows/bug.md")
        result, output = _quiet(vds.check_workflow_routing, ROUTING_TABLE, self.root)
        self.assertFalse(result)
        self.assertIn("流程檔不存在: .agents/workflows/hotfix.md", output)

    def test_unlinked_workflow_file_fails(self):
        self._write_three_workflows()
        self._write(".agents/workflows/perf.md")
        result, output = _quiet(vds.check_workflow_routing, ROUTING_TABLE, self.root)
        self.assertFalse(result)
        self.assertIn("未登錄於 AGENTS.md 分流表: .agents/workflows/perf.md", output)

    def test_agents_without_any_workflow_link_fails(self):
        self._write_three_workflows()
        result, output = _quiet(vds.check_workflow_routing, "# 沒有分流表\n", self.root)
        self.assertFalse(result)
        self.assertIn("未連結任何", output)

    def test_missing_workflows_directory_reports_every_link(self):
        result, output = _quiet(vds.check_workflow_routing, ROUTING_TABLE, self.root)
        self.assertFalse(result)
        self.assertEqual(output.count("流程檔不存在"), 3)


class TestBugReportDirectory(_TempRootCase):
    def setUp(self):
        super().setUp()
        self.index = self._write("docs/README.md", "| 0026 | [Bug-0026](./bugs/0026-empty-file-crash.md) |\n")
        self.bugs = self.root / "docs" / "bugs"
        self._write("docs/bugs/README.md", "# 說明\n")
        self._orig_root = vds.ROOT_DIR
        vds.ROOT_DIR = self.root
        self.addCleanup(setattr, vds, "ROOT_DIR", self._orig_root)

    def test_indexed_report_passes_and_readme_is_ignored(self):
        self._write("docs/bugs/0026-empty-file-crash.md", "# 缺陷\n")
        result, output = _quiet(vds.check_directory_docs, self.bugs, "缺陷報告", self.index)
        self.assertTrue(result)
        self.assertIn("(1 個)", output)

    def test_bad_filename_fails(self):
        self._write("docs/bugs/bug-empty-file.md", "# 缺陷\n")
        result, output = _quiet(vds.check_directory_docs, self.bugs, "缺陷報告", self.index)
        self.assertFalse(result)
        self.assertIn("檔名格式不符", output)

    def test_report_missing_from_index_fails(self):
        self._write("docs/bugs/0027-redis-timeout.md", "# 缺陷\n")
        result, output = _quiet(vds.check_directory_docs, self.bugs, "缺陷報告", self.index)
        self.assertFalse(result)
        self.assertIn("未登載於", output)
        self.assertIn("0027-redis-timeout.md", output)


class TestBugReportQualityScope(unittest.TestCase):
    def test_bug_report_without_scope_declaration_fails(self):
        report = "# 缺陷報告\n## 5. 缺陷驗收條件 (BC)\n* BC-1：回歸測試由紅轉綠。\n"
        result, output = _quiet(vds.check_quality_ac_specs, [("0026-x.md", report)])
        self.assertFalse(result)
        self.assertIn("缺少「品質評測範圍：是/否」宣告: 0026-x.md", output)

    def test_bug_report_declared_out_of_scope_passes(self):
        report = "# 缺陷報告\n## 5. 缺陷驗收條件 (BC)\n* BC-1：回歸測試由紅轉綠。\n\n品質評測範圍：否\n"
        result, output = _quiet(vds.check_quality_ac_specs, [("0026-x.md", report)])
        self.assertTrue(result)
        self.assertNotIn("[FAIL]", output)

    def test_shipped_bug_template_declares_scope(self):
        template = (_SCRIPT.parents[2] / "bug-triage" / "references" / "bug_report_template.md").read_text(encoding="utf-8")
        self.assertFalse(vds.quality_scope(template))
        self.assertIsNotNone(vds.QUALITY_SCOPE_PATTERN.search(template))


class TestTemplateMirrors(_TempRootCase):
    MIRRORS = {"qa_report_template.md": ".agents/skills/qa-testing/references/qa_report_template.md"}

    def test_identical_content_with_different_newlines_passes(self):
        self._write(self.MIRRORS["qa_report_template.md"], "# 範本\n第一行\n")
        (self.root / "docs" / "templates").mkdir(parents=True)
        (self.root / "docs" / "templates" / "qa_report_template.md").write_bytes("# 範本\r\n第一行\r\n".encode("utf-8"))
        result, output = _quiet(vds.check_template_mirrors, self.root, self.MIRRORS)
        self.assertTrue(result)
        self.assertIn("一致 (1 個)", output)

    def test_drifted_mirror_fails(self):
        self._write(self.MIRRORS["qa_report_template.md"], "# 範本\n新增第 9 節\n")
        self._write("docs/templates/qa_report_template.md", "# 範本\n")
        result, output = _quiet(vds.check_template_mirrors, self.root, self.MIRRORS)
        self.assertFalse(result)
        self.assertIn("鏡像與正本不一致", output)

    def test_missing_mirror_fails(self):
        self._write(self.MIRRORS["qa_report_template.md"], "# 範本\n")
        result, output = _quiet(vds.check_template_mirrors, self.root, self.MIRRORS)
        self.assertFalse(result)
        self.assertIn("缺少範本鏡像", output)

    def test_missing_source_fails(self):
        self._write("docs/templates/qa_report_template.md", "# 範本\n")
        result, output = _quiet(vds.check_template_mirrors, self.root, self.MIRRORS)
        self.assertFalse(result)
        self.assertIn("範本正本不存在", output)

    def test_registered_mirrors_cover_every_docs_template(self):
        templates_dir = _SCRIPT.parents[4] / "docs" / "templates"
        on_disk = {p.name for p in templates_dir.glob("*.md")}
        self.assertEqual(on_disk, set(vds.TEMPLATE_MIRRORS))


if __name__ == "__main__":
    unittest.main()
