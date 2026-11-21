"""audit_guardrails.py 守門缺口回歸測試（Spec-0039：Bug-0031、Bug-0032、Bug-0033）。

每個案例在暫存目錄建立最小假專案（複製閘門腳本與 lib，改寫 project.toml 為 app/ 分層），
以真實 CLI 執行 audit_guardrails.py。內容全為合成資料，不讀取本機 data/ 或 resume/。
屬閉環核心自我測試，移植後仍須通過。
"""
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[1]
SCRIPT_REL = Path(".agents/skills/code-review/scripts/audit_guardrails.py")


def _rewrite_config(text: str) -> str:
    text = re.sub(r'"src/', '"app/', text)
    text = re.sub(r'= "src"', '= "app"', text)
    text = re.sub(r"forbidden_hash_prefixes = \[[^\]]*\]", "forbidden_hash_prefixes = []", text)
    text = re.sub(r"\[\[guardrails\.url_exceptions\]\]\n(?:[^\[\n].*\n)*", "", text)
    text = text.replace("ignore_scan_dirs = [", "url_exceptions = []\nignore_scan_dirs = [", 1)
    text = re.sub(r'module = "[^"]*"', 'module = "app/infrastructure/config.py"', text, count=1)
    return text


class MiniProject:
    """最小假專案：分層目錄、設定模組、.env.example、.gitignore 皆齊備時應零 P0。"""

    def __init__(self, root: Path):
        self.root = root
        script_dir = root / SCRIPT_REL.parent
        script_dir.mkdir(parents=True)
        shutil.copy2(AGENTS_DIR / "skills" / "code-review" / "scripts" / "audit_guardrails.py", script_dir)
        shutil.copytree(AGENTS_DIR / "lib", root / ".agents" / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        config = _rewrite_config((AGENTS_DIR / "project.toml").read_text(encoding="utf-8"))
        (root / ".agents" / "project.toml").write_text(config, encoding="utf-8")
        self.config = tomllib.loads(config)
        for layer in ("domain", "application", "infrastructure", "interfaces"):
            (root / "app" / layer).mkdir(parents=True)
        self.write("app/domain/models.py", "from dataclasses import dataclass\n\n\n@dataclass\nclass Item:\n    name: str\n")
        self.write("app/infrastructure/config.py", 'import os\n\nTOKEN = os.environ.get("DEMO_TOKEN")\n')
        self.write(".env.example", "DEMO_TOKEN=\n")
        self.write(".gitignore", "\n".join(self.config["guardrails"]["required_gitignore"]) + "\n")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run(self):
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", str(self.root / SCRIPT_REL)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        return proc.returncode, proc.stdout + proc.stderr


class GuardrailGapTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = MiniProject(Path(self._tmp.name) / "demo_proj")

    def assert_p0(self, *fragments):
        code, out = self.project.run()
        self.assertEqual(code, 1, out)
        for fragment in fragments:
            self.assertIn(fragment, out)


class TestBaseline(GuardrailGapTestCase):
    def test_complete_mini_project_has_no_p0(self):
        code, out = self.project.run()
        self.assertEqual(code, 0, out)


class TestBug0031NestedLayerModules(GuardrailGapTestCase):
    """Bug-0031：Domain／Application 子資料夾內的違規模組須被檢出，訊息含相對路徑"""

    def test_nested_domain_module_importing_third_party_is_p0(self):
        self.project.write("app/domain/sub/nested.py", "import redis\n")
        self.assert_p0("app/domain/sub/nested.py")

    def test_nested_application_module_importing_outer_layer_is_p0(self):
        self.project.write("app/application/flows/runner.py", "from app.infrastructure.config import TOKEN\n")
        self.assert_p0("app/application/flows/runner.py")


if __name__ == "__main__":
    unittest.main()
