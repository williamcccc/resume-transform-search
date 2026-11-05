import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import importlib.util

# 動態匯入技能腳本
script_path = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "resume-vector-search" / "scripts" / "run_resume_search.py"
spec = importlib.util.spec_from_file_location("run_resume_search", str(script_path))
run_resume_search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_resume_search)


class TestResumeSearchSkillScript(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_check_prerequisites_missing_key(self):
        with patch.object(Path, "exists", return_value=False):
            ok, msg = run_resume_search.check_prerequisites()
            self.assertFalse(ok)
            self.assertIn("GEMINI_API_KEY", msg)

    @patch("redis.from_url")
    def test_check_prerequisites_success(self, mock_redis_from_url):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_from_url.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key", "REDIS_URL": "redis://localhost:6379/0"}):
            ok, msg = run_resume_search.check_prerequisites()
            self.assertTrue(ok)
            self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
