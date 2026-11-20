"""project_config 與閘門腳本設定化之白箱單元測試（Spec-0028）。

設定檔一律於暫存目錄動態建構，不讀取本機 data/ 或 resume/。
"""
import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = PROJECT_ROOT / ".agents" / "lib"
GUARDRAIL_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "code-review" / "scripts" / "audit_guardrails.py"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
import project_config  # noqa: E402

VALID_TOML = """
[layers]
enabled = true
src = "app"
domain = "app/core"
application = "app/services"
infrastructure = "app/adapters"
interfaces = "app/entry"
domain_interfaces = "app/core/ports.py"

[config]
module = "app/adapters/settings.py"
env_example = ".env.example"

[guardrails]
url_schemes = ["https"]
api_key_patterns = ['sk-[a-z0-9]{8}']
prompt_indicators = ["你是一個"]
eval_only_modules = []
required_gitignore = [".env"]
ignore_scan_dirs = [".git"]

[[guardrails.url_exceptions]]
path = "app/adapters/client.py"
reason = "本機開發預設值"

[privacy]
forbidden_hash_prefixes = []
safe_email_domains = ["example.com"]
safe_filename_stems = ["sample"]
sensitive_dirs = []
personal_filename_keywords = []
locale_patterns = []

[docs]
quality_ac_enforced_from = 1
agents_max_lines = 200
"""


def _load_guardrails():
    spec = importlib.util.spec_from_file_location("audit_guardrails_config", GUARDRAIL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestLoadProjectConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / ".agents").mkdir()
        self.config_path = self.root / ".agents" / "project.toml"

    def write(self, text):
        self.config_path.write_text(text, encoding="utf-8")

    def assert_config_error(self, fragment, sections=None):
        with self.assertRaises(project_config.ProjectConfigError) as ctx:
            project_config.load_project_config(self.root, sections)
        self.assertIn(fragment, str(ctx.exception))

    def test_valid_config_loads_all_sections(self):
        self.write(VALID_TOML)
        data = project_config.load_project_config(self.root)
        self.assertEqual(data["layers"]["domain"], "app/core")
        self.assertEqual(data["guardrails"]["url_exceptions"][0]["reason"], "本機開發預設值")

    def test_missing_file_raises(self):
        self.assert_config_error("找不到專案設定檔")

    def test_invalid_toml_raises_with_chained_cause(self):
        self.write("[layers\nenabled = true\n")
        with self.assertRaises(project_config.ProjectConfigError) as ctx:
            project_config.load_project_config(self.root)
        self.assertIn("語法錯誤", str(ctx.exception))
        self.assertIsNotNone(ctx.exception.__cause__)

    def test_missing_section_raises(self):
        self.write(VALID_TOML.replace("[docs]", "[docs_renamed]"))
        self.assert_config_error("缺少區段 [docs]")

    def test_missing_key_names_section_and_key(self):
        self.write(VALID_TOML.replace("agents_max_lines = 200\n", ""))
        self.assert_config_error("[docs].agents_max_lines")

    def test_wrong_types_raise(self):
        cases = [
            ("enabled = true", 'enabled = "yes"', "[layers].enabled"),
            ("quality_ac_enforced_from = 1", "quality_ac_enforced_from = true", "[docs].quality_ac_enforced_from"),
            ('url_schemes = ["https"]', 'url_schemes = "https"', "[guardrails].url_schemes"),
            ('src = "app"', 'src = ""', "[layers].src"),
            ('locale_patterns = []', 'locale_patterns = [1]', "[privacy].locale_patterns"),
        ]
        for old, new, fragment in cases:
            with self.subTest(fragment=fragment):
                self.write(VALID_TOML.replace(old, new, 1))
                self.assert_config_error(fragment)

    def test_url_exception_without_reason_raises(self):
        self.write(VALID_TOML.replace('reason = "本機開發預設值"\n', ""))
        self.assert_config_error("缺少必填欄位 reason")

    def test_url_exception_blank_reason_raises(self):
        self.write(VALID_TOML.replace('reason = "本機開發預設值"', 'reason = "  "'))
        self.assert_config_error("缺少必填欄位 reason")

    def test_empty_url_exceptions_allowed(self):
        text = VALID_TOML.replace(
            '[[guardrails.url_exceptions]]\npath = "app/adapters/client.py"\nreason = "本機開發預設值"\n', ""
        ).replace('ignore_scan_dirs = [".git"]', 'ignore_scan_dirs = [".git"]\nurl_exceptions = []')
        self.write(text)
        data = project_config.load_project_config(self.root)
        self.assertEqual(data["guardrails"]["url_exceptions"], [])

    def test_only_requested_sections_are_validated(self):
        self.write(VALID_TOML.split("[layers]")[0] + "[docs]\nquality_ac_enforced_from = 1\nagents_max_lines = 10\n")
        data = project_config.load_project_config(self.root, ("docs",))
        self.assertEqual(data["docs"]["agents_max_lines"], 10)
        self.assert_config_error("缺少區段 [layers]", ("layers",))

    def test_unknown_section_request_raises(self):
        self.write(VALID_TOML)
        self.assert_config_error("未定義的設定區段", ("nope",))

    def test_repository_config_is_valid(self):
        data = project_config.load_project_config(PROJECT_ROOT)
        self.assertTrue(data["layers"]["enabled"])
        for item in data["guardrails"]["url_exceptions"]:
            self.assertTrue(item["reason"].strip())


class TestGuardrailHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guardrails()

    def test_workspace_pattern_windows_root_is_case_insensitive_on_drive(self):
        pattern = self.guard.workspace_path_pattern(PureWindowsPath("D:/Work/demo_proj"))
        self.assertTrue(pattern.search("see d:/Work/demo_proj/file.md"))
        self.assertTrue(pattern.search(r"see D:\\Work\\demo_proj"))
        self.assertIsNone(pattern.search("see D:/Work/other_proj"))

    def test_workspace_pattern_posix_root(self):
        pattern = self.guard.workspace_path_pattern(PurePosixPath("/home/dev/demo_proj"))
        self.assertTrue(pattern.search("cd /home/dev/demo_proj/src"))
        self.assertIsNone(pattern.search("cd /home/dev/other"))

    def test_workspace_pattern_drive_root_never_matches(self):
        pattern = self.guard.workspace_path_pattern(PureWindowsPath("D:/"))
        self.assertIsNone(pattern.search("D:/anything/at/all"))

    def test_empty_list_compiles_to_never_match(self):
        never = self.guard._compile_or_never(r"(?:)", [])
        self.assertIsNone(never.search("任何文字"))
        self.assertIsNone(never.match("任何文字"))
        self.assertEqual(list(never.finditer("任何文字")), [])
        self.assertIsInstance(self.guard._compile_or_never("abc", ["x"]), re.Pattern)

    def test_outer_layer_detection_uses_configured_packages(self):
        infra = self.guard.INFRASTRUCTURE_PACKAGE
        self.assertTrue(self.guard._is_outer_layer(infra))
        self.assertTrue(self.guard._is_outer_layer(infra + ".stores"))
        self.assertFalse(self.guard._is_outer_layer(infra + "_extra"))
        self.assertFalse(self.guard._is_outer_layer(self.guard.DOMAIN_PACKAGE))

    def test_url_exceptions_come_from_config(self):
        data = project_config.load_project_config(PROJECT_ROOT, ("guardrails",))
        expected = {Path(item["path"]) for item in data["guardrails"]["url_exceptions"]}
        self.assertEqual(self.guard.URL_EXCEPTION_PATHS, expected)


if __name__ == "__main__":
    unittest.main()
