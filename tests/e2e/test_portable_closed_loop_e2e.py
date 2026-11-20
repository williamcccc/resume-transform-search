"""
閉環移植演練端到端實測（Spec-0028 AC-3、AC-6；Spec-0030 AC-1、AC-2、AC-4、AC-6）
將閉環檔案複製到暫存目錄中的最小假專案，依 .agents/PORTING.md 操作後以真實 CLI 執行三支閘門腳本。
不修改專案本身的任何檔案；假專案內容全為合成資料。
安全掃描案例使用本專案 .venv-tools 內之真實 Semgrep／pip-audit；未安裝時略過，無法連網時只驗證不阻斷。
"""
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUDIT_REL = Path(".agents/skills/code-review/scripts/audit_guardrails.py")
VERIFY_REL = Path(".agents/skills/doc-sync/scripts/verify_doc_sync.py")
SCAN_REL = Path(".agents/skills/code-review/scripts/security_scan.py")
FRAMEWORK_REL = Path(".agents/skills/feature-design/references/security_nfr_framework.md")
TOOLS_VENV = PROJECT_ROOT / ".venv-tools"
CORS_SOURCE = (
    "from fastapi import FastAPI\n"
    "from fastapi.middleware.cors import CORSMiddleware\n\n"
    "app = FastAPI()\n"
    "app.add_middleware(\n"
    "    CORSMiddleware,\n"
    '    allow_origins=["*"],\n'
    "    allow_credentials=True,\n"
    ")\n"
)
BUSINESS_SKILLS = ("resume-vector-indexing", "resume-vector-search")
TEMPLATE_SOURCES = (
    ".agents/skills/feature-design/references/prd_template.md",
    ".agents/skills/feature-design/references/tech_spec_template.md",
    ".agents/skills/qa-testing/references/test_case_template.md",
    ".agents/skills/qa-testing/references/qa_report_template.md",
    ".agents/skills/bug-triage/references/bug_report_template.md",
)


def _rewrite_project_toml(text: str) -> str:
    """依 PORTING.md 第 3 步改寫設定：換分層路徑、清空指紋與豁免、品質門檻改為 1。"""
    text = re.sub(r'"src/', '"app/', text)
    text = re.sub(r'= "src"', '= "app"', text)
    text = re.sub(r"forbidden_hash_prefixes = \[[^\]]*\]", "forbidden_hash_prefixes = []", text)
    text = re.sub(r"\[\[guardrails\.url_exceptions\]\]\n(?:[^\[\n].*\n)*", "", text)
    text = text.replace("ignore_scan_dirs = [", "url_exceptions = []\nignore_scan_dirs = [", 1)
    text = re.sub(r"quality_ac_enforced_from = \d+", "quality_ac_enforced_from = 1", text)
    # Spec-0030：安全門檻從第一份規格起、掃描範圍與需求檔改為新專案、工具沿用本機 .venv-tools
    text = re.sub(r"security_ac_enforced_from = \d+", "security_ac_enforced_from = 1", text)
    text = re.sub(r"scan_paths = \[[^\]]*\]", 'scan_paths = ["app"]', text)
    text = re.sub(r"dependency_files = \[[^\]]*\]", 'dependency_files = ["requirements.txt"]', text)
    text = re.sub(r'tools_venv = "[^"]*"', f'tools_venv = "{TOOLS_VENV.as_posix()}"', text)
    return text


class TestPortableClosedLoopE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "demo_proj"
        self.root.mkdir()
        self._port()

    # ---- 移植步驟 ----
    def _port(self):
        ignore = shutil.ignore_patterns("__pycache__")
        for name in (".agents", ".claude"):
            shutil.copytree(PROJECT_ROOT / name, self.root / name, ignore=ignore)
        for name in ("AGENTS.md", "CLAUDE.md"):
            shutil.copy2(PROJECT_ROOT / name, self.root / name)
        for skill in BUSINESS_SKILLS:
            shutil.rmtree(self.root / ".agents" / "skills" / skill)
            shutil.rmtree(self.root / ".claude" / "skills" / skill)

        # PORTING.md：基準檔是原專案的發現，不得帶走
        (self.root / ".agents" / "security_baseline.json").unlink()
        config = self.root / ".agents" / "project.toml"
        config.write_text(_rewrite_project_toml(config.read_text(encoding="utf-8")), encoding="utf-8")
        self.config = tomllib.loads(config.read_text(encoding="utf-8"))

        docs = self.root / "docs"
        for sub in ("specs", "qa_reports", "adr", "bugs", "templates"):
            (docs / sub).mkdir(parents=True)
        (docs / "README.md").write_text("# 文件索引\n\n（尚無規格）\n", encoding="utf-8")
        (docs / "adr" / "README.md").write_text("# ADR 索引\n\n（尚無 ADR）\n", encoding="utf-8")
        for source in TEMPLATE_SOURCES:
            shutil.copy2(self.root / source, docs / "templates" / Path(source).name)
        (self.root / "REQUIREMENTS.md").write_text("# 需求\n\n示範專案需求。\n", encoding="utf-8")
        (self.root / "ARCHITECTURE.md").write_text("# 架構\n\n示範專案架構。\n", encoding="utf-8")

        # 最小假專案原始碼
        core = self.root / "app" / "domain"
        core.mkdir(parents=True)
        (core / "models.py").write_text("from dataclasses import dataclass\n\n\n@dataclass\nclass Item:\n    name: str\n", encoding="utf-8")
        infra = self.root / "app" / "infrastructure"
        infra.mkdir(parents=True)
        (infra / "config.py").write_text("import os\n\nTOKEN = os.environ.get(\"DEMO_TOKEN\")\n", encoding="utf-8")
        (self.root / ".env.example").write_text("DEMO_TOKEN=\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("# 示範專案相依\n", encoding="utf-8")
        gitignore = "\n".join(self.config["guardrails"]["required_gitignore"]) + "\n"
        (self.root / ".gitignore").write_text(gitignore, encoding="utf-8")

    def run_script(self, rel, timeout=120):
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", str(self.root / rel)],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout + proc.stderr

    def set_config(self, old, new):
        path = self.root / ".agents" / "project.toml"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    # ---- AC-6：移植演練 ----
    def test_p1_ported_project_passes_both_gates(self):
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 0, out)
        code, out = self.run_script(AUDIT_REL)
        self.assertEqual(code, 0, out)
        self.assertIn("Domain 層純潔性驗證", out)

    def test_p2_original_fingerprints_absent_after_porting(self):
        original = tomllib.loads((PROJECT_ROOT / ".agents" / "project.toml").read_text(encoding="utf-8"))
        prefixes = original["privacy"]["forbidden_hash_prefixes"]
        self.assertTrue(prefixes)
        leaked = []
        for path in self.root.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                leaked.extend(path.relative_to(self.root).as_posix() for p in prefixes if p in text)
        self.assertEqual(leaked, [])

    # ---- AC-3：設定缺漏與開關 ----
    def test_p3_missing_config_exits_2_for_both_scripts(self):
        (self.root / ".agents" / "project.toml").unlink()
        for rel in (AUDIT_REL, VERIFY_REL):
            with self.subTest(script=rel.name):
                code, out = self.run_script(rel)
                self.assertEqual(code, 2, out)
                self.assertIn("找不到專案設定檔", out)

    def test_p4_missing_key_names_the_key(self):
        self.set_config("agents_max_lines = 200\n", "")
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 2, out)
        self.assertIn("[docs].agents_max_lines", out)

    def test_p5_url_exception_without_reason_exits_2(self):
        self.set_config(
            "url_exceptions = []",
            'url_exceptions = [{ path = "app/infrastructure/client.py" }]',
        )
        code, out = self.run_script(AUDIT_REL)
        self.assertEqual(code, 2, out)
        self.assertIn("缺少必填欄位 reason", out)

    def test_p6_layers_switch_controls_domain_check(self):
        (self.root / "app" / "domain" / "leaky.py").write_text("import requests\n", encoding="utf-8")
        code, out = self.run_script(AUDIT_REL)
        self.assertEqual(code, 1, out)
        self.assertIn("Domain 引入外部第三方套件", out)

        self.set_config("enabled = true", "enabled = false")
        code, out = self.run_script(AUDIT_REL)
        self.assertEqual(code, 0, out)
        self.assertIn("[Skip] DDD 分層檢查已停用", out)

    def test_p7_unknown_locale_pattern_exits_2(self):
        self.set_config('locale_patterns = ["tw_mobile", "tw_landline", "tw_id"]', 'locale_patterns = ["xx_phone"]')
        code, out = self.run_script(AUDIT_REL)
        self.assertEqual(code, 2, out)
        self.assertIn("xx_phone", out)

    def test_p8_quality_gate_threshold_follows_config(self):
        spec = "# 規格\n\n## 驗收標準\n* AC-1：示範。\n"
        (self.root / "docs" / "specs" / "0001-demo-spec.md").write_text(spec, encoding="utf-8")
        readme = self.root / "docs" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n[Spec-0001](./specs/0001-demo-spec.md)\n", encoding="utf-8")
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 1, out)
        self.assertIn("0001-demo-spec.md", out)

    # ---- Spec-0030：安全與非功能需求通用核心 ----
    def test_s1_core_framework_cannot_be_deleted(self):
        (self.root / FRAMEWORK_REL).unlink()
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 1, out)
        self.assertIn("閉環通用核心檔缺失", out)
        self.assertIn("security_nfr_framework.md", out)

    def test_s2_missing_security_trait_exits_2(self):
        path = self.root / ".agents" / "project.toml"
        text, count = re.subn(r"^uses_llm = true[^\n]*\n", "", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        self.assertEqual(count, 1)
        path.write_text(text, encoding="utf-8")
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 2, out)
        self.assertIn("[security].uses_llm", out)

    def test_s3_not_applicable_without_reason_exits_2(self):
        path = self.root / ".agents" / "project.toml"
        text = re.sub(r'(\[\[security\.not_applicable\]\]\nitem = "[^"]*"\n)reason = "[^"]*"\n', r"\1", path.read_text(encoding="utf-8"), count=1)
        path.write_text(text, encoding="utf-8")
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 2, out)
        self.assertIn("缺少必填欄位 reason", out)

    def test_s4_security_scope_gate_enforced_from_first_spec(self):
        spec = "# 規格\n\n## 驗收標準\n* AC-1：示範。\n\n品質評測範圍：否\n\n安全評估範圍：是\n"
        (self.root / "docs" / "specs" / "0001-demo-spec.md").write_text(spec, encoding="utf-8")
        readme = self.root / "docs" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n[Spec-0001](./specs/0001-demo-spec.md)\n", encoding="utf-8")
        code, out = self.run_script(VERIFY_REL)
        self.assertEqual(code, 1, out)
        self.assertIn("缺少 STRIDE 威脅表", out)
        self.assertIn("缺少 NFR-*", out)

    @unittest.skipUnless((TOOLS_VENV / "Scripts").is_dir() or (TOOLS_VENV / "bin").is_dir(),
                         "未安裝 .venv-tools（requirements-dev.txt）")
    def test_s5_security_scan_runs_and_detects_cors_wildcard(self):
        (self.root / "app" / "interfaces").mkdir()
        (self.root / "app" / "interfaces" / "server.py").write_text(CORS_SOURCE, encoding="utf-8")
        code, out = self.run_script(SCAN_REL, timeout=600)
        self.assertEqual(code, 0, out)  # 規則為 WARNING → P1，不阻斷
        if "未執行：semgrep" in out:
            self.skipTest("無法連網下載 Semgrep 規則集")
        self.assertIn("wildcard-cors", out)
        self.assertIn("[P1]", out)


if __name__ == "__main__":
    unittest.main()
