"""閉環結構自動檢查白箱單元測試（Spec-0034 C1–C8）。

框架表、設定與標記樣本一律於記憶體或暫存目錄建構，不讀取本機敏感目錄（`privacy.sensitive_dirs`）。
屬閉環核心自我測試，移植後仍須通過。
"""
import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "skills" / "doc-sync" / "scripts" / "verify_doc_sync.py"
_spec = importlib.util.spec_from_file_location("verify_doc_sync_structure", _SCRIPT)
vds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vds)

CONDITIONS = {9: "技術：JWT", 10: "技術：OAuth", 17: "技術：WebRTC", 3: "特徵：`web_interface`", 7: "特徵：同 V6"}


def framework(rows=None):
    rows = rows if rows is not None else [(n, CONDITIONS.get(n, "一律")) for n in range(1, 18)]
    table = "\n".join(f"| V{n} | 章名 | {cond} | 重點 |" for n, cond in rows)
    return f"# 框架\n\n## 四、標準對照\n\n| 章 | 名稱 | 適用條件 | 重點 |\n| :---: | :--- | :--- | :--- |\n{table}\n\n## 五、其他\n"


def security(not_applicable=("V9、V10、V17",), in_use=()):
    return {
        "not_applicable": [{"item": item, "reason": "未使用"} for item in not_applicable],
        "tech_chapters_in_use": list(in_use),
    }


def run(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


class TestAsvsChapterCoverage(unittest.TestCase):
    """C1–C4"""

    def test_complete_table_with_declared_tech_chapters_passes(self):
        ok, out = run(vds.check_asvs_chapter_coverage, framework(), security())
        self.assertTrue(ok, out)
        self.assertIn("17 章；技術條件章節 3 章皆已宣告", out)

    def test_missing_and_duplicated_chapters_fail(self):
        rows = [(n, "一律") for n in range(1, 18) if n != 5] + [(2, "一律")]
        ok, out = run(vds.check_asvs_chapter_coverage, framework(rows), security(()))
        self.assertFalse(ok)
        self.assertIn("缺 [5]", out)
        self.assertIn("重複 [2]", out)

    def test_chapter_beyond_range_fails(self):
        rows = [(n, "一律") for n in range(1, 19)]
        ok, out = run(vds.check_asvs_chapter_coverage, framework(rows), security(()))
        self.assertFalse(ok)
        self.assertIn("超出範圍 [18]", out)

    def test_unclassified_condition_fails(self):
        rows = [(n, "同 V6" if n == 8 else "一律") for n in range(1, 18)]
        ok, out = run(vds.check_asvs_chapter_coverage, framework(rows), security(()))
        self.assertFalse(ok)
        self.assertIn("V8 適用條件未歸屬", out)

    def test_undeclared_tech_chapter_fails(self):
        ok, out = run(vds.check_asvs_chapter_coverage, framework(), security(("V9、V10",)))
        self.assertFalse(ok)
        self.assertIn("V17 為技術條件章節，未於 tech_chapters_in_use 或 not_applicable 宣告", out)

    def test_tech_chapter_in_use_counts_as_declared(self):
        ok, out = run(vds.check_asvs_chapter_coverage, framework(), security(("V10、V17",), in_use=("V9",)))
        self.assertTrue(ok, out)

    def test_tech_chapter_in_both_lists_fails(self):
        ok, out = run(vds.check_asvs_chapter_coverage, framework(), security(("V9、V10、V17",), in_use=("V9",)))
        self.assertFalse(ok)
        self.assertIn("V9 同時列於", out)

    def test_not_applicable_out_of_range_and_invalid_in_use_fail(self):
        ok, out = run(vds.check_asvs_chapter_coverage, framework(), security(("V9、V10、V17、V18",), in_use=("X1",)))
        self.assertFalse(ok)
        self.assertIn("範圍外章節 ['V18']", out)
        self.assertIn("tech_chapters_in_use 含無效章節：X1", out)

    def test_missing_section_fails(self):
        ok, out = run(vds.check_asvs_chapter_coverage, "# 無第四節\n", security())
        self.assertFalse(ok)

    def test_repository_framework_and_config_pass(self):
        text = (vds.ROOT_DIR / vds.FRAMEWORK_FILE).read_text(encoding="utf-8")
        ok, out = run(vds.check_asvs_chapter_coverage, text, vds.PROJECT_CONFIG["security"])
        self.assertTrue(ok, out)


class TestInstanceFilesAndSkills(unittest.TestCase):
    """C5、C8"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)

    def test_required_instance_files(self):
        for rel in vds.REQUIRED_INSTANCE_FILES:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("# 實例\n", encoding="utf-8")
        ok, _ = run(vds.check_required_instance_files, self.root)
        self.assertTrue(ok)
        (self.root / vds.REQUIRED_INSTANCE_FILES[0]).unlink()
        ok, out = run(vds.check_required_instance_files, self.root)
        self.assertFalse(ok)
        self.assertIn(vds.REQUIRED_INSTANCE_FILES[0].as_posix(), out)

    def test_business_skills_must_exist_in_both_trees(self):
        ok, _ = run(vds.check_business_skills, [], self.root)
        self.assertTrue(ok)
        (self.root / ".agents" / "skills" / "demo-skill").mkdir(parents=True)
        ok, out = run(vds.check_business_skills, ["demo-skill"], self.root)
        self.assertFalse(ok)
        self.assertIn(".claude/skills/demo-skill", out)
        (self.root / ".claude" / "skills" / "demo-skill").mkdir(parents=True)
        ok, _ = run(vds.check_business_skills, ["demo-skill"], self.root)
        self.assertTrue(ok)


class TestProjectMarkers(unittest.TestCase):
    """C7"""

    ALLOWED = "#### 本專案紅線（移植時整節改寫）<!-- 專案專屬：整節 -->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        (self.root / ".agents" / "skills").mkdir(parents=True)
        (self.root / ".agents" / "project").mkdir(parents=True)

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")

    def test_inline_code_and_fenced_blocks_are_not_markers(self):
        text = "說明：以 `<!-- 專案專屬` 標記\n```\n<!-- 專案專屬 -->\n```\n真的<!-- 專案專屬 -->\n"
        self.assertEqual([n for n, _ in vds.find_project_markers(text)], [5])

    def test_single_allowed_marker_passes_and_project_dir_is_excluded(self):
        self.write("AGENTS.md", "# 憲法\n" + self.ALLOWED)
        self.write(".agents/project/profile.md", "本專案<!-- 專案專屬 -->\n")
        self.write(".agents/skills/x.md", "說明 `<!-- 專案專屬` 寫法\n")
        ok, out = run(vds.check_project_markers, self.root)
        self.assertTrue(ok, out)

    def test_marker_in_core_file_fails_with_location(self):
        self.write("AGENTS.md", self.ALLOWED)
        self.write(".agents/skills/x.md", "第一行\n專案規則<!-- 專案專屬 -->\n")
        ok, out = run(vds.check_project_markers, self.root)
        self.assertFalse(ok)
        self.assertIn(".agents/skills/x.md:2", out)

    def test_missing_or_extra_allowed_marker_fails(self):
        self.write("AGENTS.md", "# 憲法\n")
        ok, out = run(vds.check_project_markers, self.root)
        self.assertFalse(ok)
        self.assertIn("實際 0 處", out)
        self.write("AGENTS.md", self.ALLOWED + "規則<!-- 專案專屬 -->\n")
        ok, out = run(vds.check_project_markers, self.root)
        self.assertFalse(ok)
        self.assertIn("AGENTS.md:2", out)


if __name__ == "__main__":
    unittest.main()
