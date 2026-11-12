"""audit_guardrails.check_eval_only_imports 白箱單元測試：src/ 不得 import 評測專用套件（ragas）。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUARDRAIL_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "code-review" / "scripts" / "audit_guardrails.py"


def _load_guardrails():
    spec = importlib.util.spec_from_file_location("audit_guardrails_eval_only", GUARDRAIL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCheckEvalOnlyImports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guardrails()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.src = Path(self._tmp.name) / "src"
        (self.src / "infrastructure" / "llm").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel: str, code: str) -> None:
        (self.src / rel).write_text(code, encoding="utf-8")

    def test_flags_import_and_from_import_in_nested_layers(self):
        self._write("infrastructure/llm/judge.py", "import ragas\nfrom ragas.metrics import Faithfulness\n")
        self._write("app.py", "import os, ragas.llms as rl\n")

        violations = self.guard.check_eval_only_imports(self.src)

        self.assertEqual(len(violations), 3)
        self.assertTrue(all("P0" in v and "評測專用套件" in v for v in violations))
        self.assertTrue(any("src/infrastructure/llm/judge.py:1" in v for v in violations))
        self.assertTrue(any("src/infrastructure/llm/judge.py:2" in v and "ragas.metrics" in v for v in violations))
        self.assertTrue(any("src/app.py:1" in v and "ragas.llms" in v for v in violations))

    def test_ignores_similar_names_relative_imports_and_strings(self):
        self._write(
            "infrastructure/llm/ok.py",
            "import ragas_like\nfrom myragas import x\nfrom . import ragas\ntext = 'import ragas'\n",
        )

        self.assertEqual(self.guard.check_eval_only_imports(self.src), [])

    def test_missing_src_dir_returns_empty(self):
        self.assertEqual(self.guard.check_eval_only_imports(Path(self._tmp.name) / "nope"), [])

    def test_syntax_error_is_reported(self):
        self._write("broken.py", "def (:\n")

        violations = self.guard.check_eval_only_imports(self.src)

        self.assertEqual(len(violations), 1)
        self.assertIn("Syntax Error", violations[0])

    def test_real_codebase_has_no_eval_only_imports(self):
        self.assertEqual(self.guard.check_eval_only_imports(), [])


if __name__ == "__main__":
    unittest.main()
