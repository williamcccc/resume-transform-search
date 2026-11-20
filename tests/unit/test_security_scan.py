"""
security_scan.py 白箱單元測試（Spec-0030 AC-4）
工具執行一律以假 runner 注入，零網路、零真實 Semgrep／pip-audit 呼叫；設定與基準檔於暫存目錄動態建構。
"""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".agents" / "skills" / "code-review" / "scripts" / "security_scan.py"
_spec = importlib.util.spec_from_file_location("security_scan", _SCRIPT)
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)

TODAY = dt.date(2026, 11, 20)

TOOLS_TOML = """
[security]
asvs_level = 1
network_exposure = "local"
web_interface = true
api_service = true
uses_llm = false
handles_pii = false
processes_untrusted_files = false
multi_user = false
not_applicable = []

[security.tools]
scan_paths = ["app"]
semgrep_configs = ["p/python"]
semgrep_block_severities = ["ERROR"]
dependency_files = ["requirements.txt"]
dependency_level = "P1"
baseline = ".agents/security_baseline.json"
tools_venv = ".venv-tools"
"""

CORS_RESULT = {
    "check_id": "python.fastapi.security.wildcard-cors.wildcard-cors",
    "path": "app/server.py",
    "start": {"line": 7},
    "extra": {"severity": "WARNING", "message": "CORS allows any origin", "lines": '    allow_origins=["*"],'},
}
ERROR_RESULT = {
    "check_id": "python.lang.security.audit.eval-detected",
    "path": "app/util.py",
    "start": {"line": 3},
    "extra": {"severity": "ERROR", "message": "eval", "lines": "eval(user_input)"},
}
PIP_AUDIT_PAYLOAD = {"dependencies": [
    {"name": "demo-lib", "version": "1.0.0", "vulns": [
        {"id": "PYSEC-0000-1", "fix_versions": ["1.0.1"], "aliases": []},
        {"id": "PYSEC-0000-1", "fix_versions": ["1.0.1"], "aliases": ["GHSA-xxxx"]},
    ]},
    {"name": "safe-lib", "version": "2.0.0", "vulns": []},
]}


def make_root(tmp: str, baseline: dict = None) -> pathlib.Path:
    root = pathlib.Path(tmp)
    (root / ".agents").mkdir()
    (root / ".agents" / "project.toml").write_text(TOOLS_TOML, encoding="utf-8")
    (root / "app").mkdir()
    (root / "requirements.txt").write_text("demo-lib==1.0.0\n", encoding="utf-8")
    scripts = root / ".venv-tools" / "Scripts"
    scripts.mkdir(parents=True)
    for name in ("semgrep.exe", "pip-audit.exe"):
        (scripts / name).write_text("", encoding="utf-8")
    if baseline is not None:
        (root / ".agents" / "security_baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    return root


class FakeRunner:
    def __init__(self, semgrep=(0, {"results": []}, ""), pip_audit=(0, {"dependencies": []}, "")):
        self.semgrep, self.pip_audit, self.calls = semgrep, pip_audit, []

    def __call__(self, cmd, cwd):
        self.calls.append(cmd)
        code, payload, stderr = self.semgrep if "semgrep" in cmd[0] else self.pip_audit
        stdout = json.dumps(payload) if isinstance(payload, dict) else payload
        return code, stdout, stderr


def run_scan(root, runner, write=None):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = ss.scan(root, runner, TODAY, write)
    return code, buffer.getvalue()


class TestParsing(unittest.TestCase):
    def test_semgrep_fingerprint_ignores_line_shift(self):
        root = pathlib.Path("/repo")
        moved = dict(CORS_RESULT, start={"line": 42})
        a, = ss.parse_semgrep({"results": [CORS_RESULT]}, root)
        b, = ss.parse_semgrep({"results": [moved]}, root)
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(a.location, "app/server.py:7")
        self.assertEqual(a.severity, "WARNING")

    def test_semgrep_fingerprint_changes_with_code(self):
        changed = dict(CORS_RESULT, extra=dict(CORS_RESULT["extra"], lines='allow_origins=["https://a.example"],'))
        a, = ss.parse_semgrep({"results": [CORS_RESULT]}, pathlib.Path("/repo"))
        b, = ss.parse_semgrep({"results": [changed]}, pathlib.Path("/repo"))
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_pip_audit_parse_and_dedupe(self):
        findings = ss.parse_pip_audit(PIP_AUDIT_PAYLOAD, "requirements.txt")
        self.assertEqual(len(findings), 2)
        unique = ss.dedupe(findings)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0].location, "requirements.txt:demo-lib==1.0.0")
        self.assertIn("1.0.1", unique[0].message)

    def test_network_error_detection(self):
        self.assertTrue(ss.is_network_error("requests.exceptions.ConnectionError: Max retries exceeded"))
        self.assertFalse(ss.is_network_error("Invalid rule schema at line 3"))


class TestBaseline(unittest.TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(ss.load_baseline(pathlib.Path("/nonexistent/baseline.json")), [])

    def test_invalid_entries_raise(self):
        cases = [
            ("{not json", "JSON 格式錯誤"),
            (json.dumps({"items": []}), "findings"),
            (json.dumps({"findings": [{"fingerprint": "x", "expires": "2027-01-01"}]}), "reason"),
            (json.dumps({"findings": [{"fingerprint": "x", "reason": "r", "expires": "明年"}]}), "YYYY-MM-DD"),
        ]
        for text, fragment in cases:
            with self.subTest(fragment=fragment), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "b.json"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ss.BaselineError) as ctx:
                    ss.load_baseline(path)
                self.assertIn(fragment, str(ctx.exception))

    def test_write_baseline_keeps_existing_and_skips_known(self):
        finding, = ss.parse_semgrep({"results": [CORS_RESULT]}, pathlib.Path("/repo"))
        existing = [{"fingerprint": "old", "reason": "r", "expires": "2027-01-01"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "b.json"
            self.assertEqual(ss.write_baseline(path, existing, [finding, finding], "既有", "2027-02-28"), 1)
            data = ss.load_baseline(path)
        self.assertEqual([e["fingerprint"] for e in data], ["old", finding.fingerprint])
        self.assertEqual(data[1]["reason"], "既有")


class TestClassify(unittest.TestCase):
    def setUp(self):
        root = pathlib.Path("/repo")
        self.warning, = ss.parse_semgrep({"results": [CORS_RESULT]}, root)
        self.error, = ss.parse_semgrep({"results": [ERROR_RESULT]}, root)
        self.dep, = ss.dedupe(ss.parse_pip_audit(PIP_AUDIT_PAYLOAD, "requirements.txt"))

    def test_severity_and_dependency_levels(self):
        result = ss.classify([self.warning, self.error, self.dep], [], TODAY, ["ERROR"], "P0")
        self.assertEqual(result.p0, [self.error, self.dep])
        self.assertEqual(result.p1, [self.warning])

    def test_active_baseline_suppresses_and_expired_blocks(self):
        baseline = [
            {"fingerprint": self.error.fingerprint, "reason": "r", "expires": "2026-11-20"},
            {"fingerprint": self.dep.fingerprint, "reason": "r", "expires": "2026-11-19"},
            {"fingerprint": "gone", "reason": "r", "expires": "2027-01-01"},
        ]
        result = ss.classify([self.error, self.dep], baseline, TODAY, ["ERROR"], "P0")
        self.assertEqual(result.baselined, [self.error])  # 到期日當天仍有效
        self.assertEqual(result.p0, [self.dep])             # 已過期即恢復阻斷
        self.assertEqual([e["fingerprint"] for e in result.stale_entries], ["gone"])


class TestScan(unittest.TestCase):
    def test_cors_wildcard_reported_as_p1_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_scan(make_root(tmp), FakeRunner(semgrep=(0, {"results": [CORS_RESULT]}, "")))
        self.assertEqual(code, 0)
        self.assertIn("[P1] semgrep python.fastapi.security.wildcard-cors", out)
        self.assertIn("P0=0 P1=1", out)

    def test_error_severity_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_scan(make_root(tmp), FakeRunner(semgrep=(0, {"results": [ERROR_RESULT]}, "")))
        self.assertEqual(code, 1)
        self.assertIn("P0=1", out)

    def test_baselined_finding_does_not_block(self):
        finding, = ss.parse_semgrep({"results": [ERROR_RESULT]}, pathlib.Path("/repo"))
        baseline = {"findings": [{"fingerprint": finding.fingerprint, "reason": "既有", "expires": "2027-01-01"}]}
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_scan(make_root(tmp, baseline), FakeRunner(semgrep=(0, {"results": [ERROR_RESULT]}, "")))
        self.assertEqual(code, 0)
        self.assertIn("基準內=1", out)

    def test_offline_tools_warn_but_do_not_block(self):
        offline = (2, "", "ConnectionError: Max retries exceeded with url")
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_scan(make_root(tmp), FakeRunner(semgrep=offline, pip_audit=offline))
        self.assertEqual(code, 0)
        self.assertIn("未執行=2", out)
        self.assertIn("[WARN] 未執行", out)

    def test_non_network_tool_error_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_scan(make_root(tmp), FakeRunner(semgrep=(2, "", "Invalid rule schema")))
        self.assertEqual(code, 1)
        self.assertIn("semgrep 執行失敗", out)

    def test_missing_tool_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            (root / ".venv-tools" / "Scripts" / "pip-audit.exe").unlink()
            original = ss.shutil.which
            ss.shutil.which = lambda name: None
            try:
                code, out = run_scan(root, FakeRunner())
            finally:
                ss.shutil.which = original
        self.assertEqual(code, 1)
        self.assertIn("找不到 pip-audit", out)

    def test_missing_scan_path_and_requirement_file_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            (root / "app").rmdir()
            (root / "requirements.txt").unlink()
            code, out = run_scan(root, FakeRunner())
        self.assertEqual(code, 1)
        self.assertIn("scan_paths 不存在: app", out)
        self.assertIn("dependency_files 不存在: requirements.txt", out)

    def test_config_error_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            (root / ".agents" / "project.toml").write_text("[security]\n", encoding="utf-8")
            code, out = run_scan(root, FakeRunner())
        self.assertEqual(code, 2)
        self.assertIn("專案設定錯誤", out)

    def test_invalid_baseline_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, {"findings": [{"fingerprint": "x"}]})
            code, out = run_scan(root, FakeRunner())
        self.assertEqual(code, 1)
        self.assertIn("缺少必填欄位 reason", out)

    def test_write_baseline_then_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            runner = FakeRunner(semgrep=(0, {"results": [ERROR_RESULT]}, ""),
                                pip_audit=(1, PIP_AUDIT_PAYLOAD, ""))
            code, out = run_scan(root, runner, write=("導入前既有發現", "2027-02-28"))
            saved = ss.load_baseline(root / ".agents" / "security_baseline.json")
        self.assertEqual(code, 0)
        self.assertIn("已將 2 筆新發現寫入基準檔", out)
        self.assertEqual(len(saved), 2)

    def test_pip_audit_called_per_requirement_file_with_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeRunner()
            run_scan(make_root(tmp), runner)
        audit_calls = [c for c in runner.calls if "pip-audit" in c[0]]
        self.assertEqual(len(audit_calls), 1)
        self.assertEqual(audit_calls[0][1:5], ["-r", "requirements.txt", "--format", "json"])


class TestCli(unittest.TestCase):
    def test_write_baseline_requires_reason_and_expires(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            ss.main(["--write-baseline", "--reason", "x"])
        self.assertEqual(ctx.exception.code, 2)

    def test_invalid_expires_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ss.main(["--write-baseline", "--reason", "x", "--expires", "2027/01/01"])


if __name__ == "__main__":
    unittest.main()
