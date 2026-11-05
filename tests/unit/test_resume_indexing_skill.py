import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import MagicMock, patch

import importlib.util

# 動態匯入技能腳本
script_path = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "resume-vector-indexing" / "scripts" / "run_resume_indexing.py"
spec = importlib.util.spec_from_file_location("run_resume_indexing", str(script_path))
run_resume_indexing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_resume_indexing)


class TestResumeIndexingSkillScript(unittest.TestCase):
    def test_resolve_markdown_dir_finds_existing_dir(self):
        with TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            markdown_dir = fake_root / "data" / "markdown_out"
            markdown_dir.mkdir(parents=True)
            (markdown_dir / "sample_resume.md").write_text("# Sample\n", encoding="utf-8")

            with patch.object(run_resume_indexing, "ROOT_DIR", fake_root):
                resolved = run_resume_indexing.resolve_markdown_dir()

            self.assertEqual(resolved, markdown_dir.resolve())

    def test_resolve_markdown_dir_with_explicit_path(self):
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir) / "custom" / "markdown_out"
            markdown_dir.mkdir(parents=True)
            (markdown_dir / "sample_resume.md").write_text("# Sample\n", encoding="utf-8")

            resolved = run_resume_indexing.resolve_markdown_dir(str(markdown_dir))

            self.assertEqual(resolved, markdown_dir.resolve())

    @patch.dict("os.environ", {}, clear=True)
    def test_check_prerequisites_missing_key(self):
        with patch.object(Path, "exists", return_value=False):
            ok, msg = run_resume_indexing.check_prerequisites()
            self.assertFalse(ok)
            self.assertIn("GEMINI_API_KEY", msg)

    @patch("redis.from_url")
    def test_check_prerequisites_success(self, mock_redis_from_url):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_from_url.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key", "REDIS_URL": "redis://localhost:6379/0"}):
            ok, msg = run_resume_indexing.check_prerequisites()
            self.assertTrue(ok)
            self.assertEqual(msg, "")

    @patch("subprocess.run")
    def test_main_passes_limit_argument(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        with TemporaryDirectory() as temp_dir:
            markdown_dir = Path(temp_dir)
            (markdown_dir / "sample_resume.md").write_text("# Sample\n", encoding="utf-8")
            with patch.object(run_resume_indexing, "resolve_markdown_dir", return_value=markdown_dir):
                with patch("sys.argv", ["run_resume_indexing.py", "sample-input", "--limit", "10", "--skip-precheck"]):
                    ret = run_resume_indexing.main()

            self.assertEqual(ret, 0)
            mock_subproc.assert_called_once()
            called_cmd = mock_subproc.call_args[0][0]
            self.assertIn("--limit", called_cmd)
            self.assertIn("10", called_cmd)



if __name__ == "__main__":
    unittest.main()
