"""
CLI 匯入隔離單元測試 (AC-30)：模擬未安裝 langgraph / langchain 時，convert_to_md 匯入與 --help 正常，
且 CLI 匯入鏈不載入任何 LangGraph / langchain 模組。以子行程執行，避免污染本行程 sys.modules。
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BLOCKER = (
    "import sys\n"
    "for name in ('langgraph', 'langchain_core', 'langchain_google_genai', 'langgraph.checkpoint.redis'):\n"
    "    sys.modules[name] = None\n"
)


def run_python(code: str):
    return subprocess.run([sys.executable, "-c", BLOCKER + code], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


class TestCliImportIsolation(unittest.TestCase):
    def test_import_convert_to_md_without_langgraph_should_succeed(self):
        result = run_python(
            "import convert_to_md\n"
            "loaded = [m for m in sys.modules if m.startswith(('langgraph', 'langchain')) and sys.modules[m] is not None]\n"
            "assert not loaded, loaded\n"
            "print('IMPORT_OK')\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr[-800:])
        self.assertIn("IMPORT_OK", result.stdout)

    def test_cli_help_without_langgraph_should_exit_zero(self):
        result = run_python(
            "import runpy\n"
            "sys.argv = ['convert_to_md.py', '--help']\n"
            "try:\n"
            "    runpy.run_path('convert_to_md.py', run_name='__main__')\n"
            "except SystemExit as exc:\n"
            "    print('EXIT', exc.code)\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr[-800:])
        self.assertIn("EXIT 0", result.stdout)


if __name__ == "__main__":
    unittest.main()
