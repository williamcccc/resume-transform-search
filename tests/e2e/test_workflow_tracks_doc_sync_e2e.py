"""
流程分軌文件檢查端到端實測（Spec-0025 / QA-0025）
將專案的規範文件複製到暫存目錄，以真實 CLI 執行 verify_doc_sync.py，
逐一注入錯誤並斷言結束碼與輸出。不修改專案本身的任何檔案。
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = Path(".agents/skills/doc-sync/scripts/verify_doc_sync.py")
COPY_DIRS = (".agents", ".claude", "docs")
COPY_FILES = ("AGENTS.md", "REQUIREMENTS.md", "ARCHITECTURE.md")

SAMPLE_BUG_REPORT = """# 缺陷報告：空檔案轉檔崩潰

> **編號**：0099｜**嚴重度**：S2｜**狀態**：處理中

## 5. 缺陷驗收條件 (BC)
* **BC-1**：回歸測試 `test_empty_file` 在 `test:` commit 失敗，在 `fix:` commit 通過。

品質評測範圍：否
"""


class TestWorkflowTracksDocSyncE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        ignore = shutil.ignore_patterns("__pycache__")
        for name in COPY_DIRS:
            shutil.copytree(PROJECT_ROOT / name, self.root / name, ignore=ignore)
        for name in COPY_FILES:
            shutil.copy2(PROJECT_ROOT / name, self.root / name)

    def run_verify(self):
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", str(self.root / SCRIPT_REL)],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        return proc.returncode, proc.stdout

    def add_index_row(self, text):
        readme = self.root / "docs" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + text, encoding="utf-8")

    def test_e1_baseline_copy_passes(self):
        code, out = self.run_verify()
        self.assertEqual(code, 0, out)
        self.assertIn("分流表與 .agents/workflows/ 流程檔一致 (4 個)", out)
        self.assertIn("範本鏡像與正本一致 (5 個)", out)
        self.assertIn("[PASS] AGENTS.md 共", out)

    def test_e8_oversized_agents_md_warns_but_passes(self):
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\n補充說明\n" * 60, encoding="utf-8")
        code, out = self.run_verify()
        self.assertEqual(code, 0, out)
        self.assertIn("[WARN] AGENTS.md 共", out)
        self.assertIn("超過上限 200 行", out)

    def test_e2_deleted_workflow_file_fails(self):
        (self.root / ".agents" / "workflows" / "hotfix.md").unlink()
        code, out = self.run_verify()
        self.assertEqual(code, 1)
        self.assertIn("流程檔不存在: .agents/workflows/hotfix.md", out)

    def test_e3_unindexed_bug_report_fails_then_passes_once_indexed(self):
        (self.root / "docs" / "bugs" / "0099-empty-file-crash.md").write_text(SAMPLE_BUG_REPORT, encoding="utf-8")
        code, out = self.run_verify()
        self.assertEqual(code, 1)
        self.assertIn("未登載於", out)
        self.add_index_row("\n| 0099 | [Bug-0099](./bugs/0099-empty-file-crash.md) |\n")
        code, out = self.run_verify()
        self.assertEqual(code, 0, out)
        # 依實際檔案數判斷，避免倉庫新增缺陷報告後失效（Bug-0029 合併後曾因寫死 1 個而失敗）
        expected = len([p for p in (self.root / "docs" / "bugs").glob("*.md") if p.name != "README.md"])
        self.assertIn(f"缺陷報告 (Bug Reports) ({expected} 個)", out)

    def test_e4_bug_report_without_quality_scope_fails(self):
        report = SAMPLE_BUG_REPORT.replace("品質評測範圍：否", "")
        (self.root / "docs" / "bugs" / "0099-empty-file-crash.md").write_text(report, encoding="utf-8")
        self.add_index_row("\n| 0099 | [Bug-0099](./bugs/0099-empty-file-crash.md) |\n")
        code, out = self.run_verify()
        self.assertEqual(code, 1)
        self.assertIn("缺少「品質評測範圍：是/否」宣告: 0099-empty-file-crash.md", out)

    def test_e5_drifted_template_mirror_fails(self):
        mirror = self.root / "docs" / "templates" / "qa_report_template.md"
        mirror.write_text(mirror.read_text(encoding="utf-8") + "\n多出一行\n", encoding="utf-8")
        code, out = self.run_verify()
        self.assertEqual(code, 1)
        self.assertIn("範本鏡像與正本不一致", out)

    def test_e6_unregistered_workflow_file_fails(self):
        (self.root / ".agents" / "workflows" / "perf.md").write_text("# 效能調校流程\n", encoding="utf-8")
        code, out = self.run_verify()
        self.assertEqual(code, 1)
        self.assertIn("未登錄於 AGENTS.md 分流表: .agents/workflows/perf.md", out)

    def test_e7_missing_bug_triage_adapter_fails(self):
        shutil.rmtree(self.root / ".claude" / "skills" / "bug-triage")
        code, out = self.run_verify()
        self.assertEqual(code, 1)
        self.assertIn("缺少 Claude Code 轉接檔: .claude/skills/bug-triage/SKILL.md", out)


if __name__ == "__main__":
    unittest.main()
