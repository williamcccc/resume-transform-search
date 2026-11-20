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
diff_base = "main"
full_scan_max_age_days = 7
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
    """依指令分派假結果；git 預設模擬「不是 git 儲存庫」。"""

    def __init__(self, semgrep=(0, {"results": []}, ""), pip_audit=(0, {"dependencies": []}, ""),
                 git_diff=None, git_untracked="", git_ok=False):
        self.semgrep, self.pip_audit, self.calls = semgrep, pip_audit, []
        self.git_diff, self.git_untracked, self.git_ok = git_diff or [], git_untracked, git_ok

    def __call__(self, cmd, cwd):
        self.calls.append(cmd)
        if cmd[0] == "git":
            if not self.git_ok:
                return 128, "", "fatal: not a git repository"
            sub = cmd[1]
            if sub == "merge-base":
                return 0, "abc123\n", ""
            if sub == "diff":
                return 0, "\n".join(self.git_diff), ""
            return 0, self.git_untracked, ""
        code, payload, stderr = self.semgrep if "semgrep" in cmd[0] else self.pip_audit
        stdout = json.dumps(payload) if isinstance(payload, dict) else payload
        return code, stdout, stderr

    def tool_calls(self, name):
        return [c for c in self.calls if name in c[0]]


def run_scan(root, runner, write=None, force_full=True):
    """既有案例預設完整掃描；觸發模式案例另行指定 force_full=False。"""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = ss.scan(root, runner, TODAY, write, force_full)
    return code, buffer.getvalue()


def write_state(root, day):
    path = root / ".venv-tools" / ss.STATE_FILE_NAME
    path.write_text(json.dumps({"last_full_scan": day.isoformat()}), encoding="utf-8")
    return path


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


class TestTriggerModes(unittest.TestCase):
    """Spec-0030 決議 10／AC-4b：程式碼與套件分開觸發，並定期完整掃描"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(self._tmp.name)
        (self.root / "app" / "server.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "note.md").write_text("n\n", encoding="utf-8")
        self.state = write_state(self.root, TODAY - dt.timedelta(days=1))

    def scan_diff(self, runner):
        return run_scan(self.root, runner, force_full=False)

    def test_code_change_scans_only_changed_files_in_scan_paths(self):
        runner = FakeRunner(git_ok=True, git_diff=["app/server.py", "docs/note.md"])
        code, out = self.scan_diff(runner)
        self.assertEqual(code, 0)
        semgrep, = runner.tool_calls("semgrep")
        self.assertEqual(semgrep[-1:], ["app/server.py"])
        self.assertNotIn("app", semgrep[:-1])
        self.assertEqual(runner.tool_calls("pip-audit"), [])
        self.assertIn("pip-audit：需求檔無變更，略過", out)
        self.assertIn("模式：差異掃描", out)

    def test_untracked_and_windows_paths_are_included_deleted_files_skipped(self):
        (self.root / "app" / "new_mod.py").write_text("y = 2\n", encoding="utf-8")
        runner = FakeRunner(git_ok=True, git_diff=["app\\server.py", "app/deleted.py"], git_untracked="app/new_mod.py\n")
        self.scan_diff(runner)
        semgrep, = runner.tool_calls("semgrep")
        self.assertEqual(semgrep[-2:], ["app/new_mod.py", "app/server.py"])

    def test_no_changes_runs_neither_tool(self):
        runner = FakeRunner(git_ok=True, git_diff=[])
        code, out = self.scan_diff(runner)
        self.assertEqual(code, 0)
        self.assertEqual(runner.tool_calls("semgrep") + runner.tool_calls("pip-audit"), [])
        self.assertIn("semgrep：scan_paths 內無程式變更，略過", out)
        self.assertNotIn("[WARN]", out)

    def test_requirement_change_runs_only_pip_audit_on_that_file(self):
        runner = FakeRunner(git_ok=True, git_diff=["requirements.txt"])
        self.scan_diff(runner)
        self.assertEqual(runner.tool_calls("semgrep"), [])
        audit, = runner.tool_calls("pip-audit")
        self.assertEqual(audit[1:3], ["-r", "requirements.txt"])

    def test_stale_full_scan_triggers_full_and_updates_state(self):
        write_state(self.root, TODAY - dt.timedelta(days=8))
        runner = FakeRunner(git_ok=True, git_diff=[])
        code, out = self.scan_diff(runner)
        self.assertEqual(code, 0)
        self.assertIn("已超過 7 天", out)
        semgrep, = runner.tool_calls("semgrep")
        self.assertEqual(semgrep[-1], "app")
        self.assertEqual(len(runner.tool_calls("pip-audit")), 1)
        self.assertEqual(ss.load_last_full_scan(self.state), TODAY)

    def test_exactly_max_age_days_stays_in_diff_mode(self):
        write_state(self.root, TODAY - dt.timedelta(days=7))
        runner = FakeRunner(git_ok=True, git_diff=[])
        _, out = self.scan_diff(runner)
        self.assertIn("模式：差異掃描", out)

    def test_missing_or_corrupt_state_triggers_full(self):
        for content in (None, "{broken"):
            with self.subTest(content=content):
                if content is None:
                    self.state.unlink(missing_ok=True)
                else:
                    self.state.write_text(content, encoding="utf-8")
                runner = FakeRunner(git_ok=True, git_diff=[])
                _, out = self.scan_diff(runner)
                self.assertIn("本機無完整掃描紀錄", out)
                self.assertEqual(len(runner.tool_calls("semgrep")), 1)

    def test_git_failure_falls_back_to_full_with_warning(self):
        runner = FakeRunner(git_ok=False)
        code, out = self.scan_diff(runner)
        self.assertEqual(code, 0)
        self.assertIn("無法取得相對 main 的 git 差異，改為完整掃描", out)
        self.assertEqual(len(runner.tool_calls("pip-audit")), 1)

    def test_forced_full_ignores_diff_and_updates_state(self):
        runner = FakeRunner(git_ok=True, git_diff=[])
        _, out = run_scan(self.root, runner, force_full=True)
        self.assertIn("指定完整掃描", out)
        self.assertEqual(len(runner.tool_calls("semgrep")), 1)
        self.assertEqual([c for c in runner.calls if c[0] == "git"], [])
        self.assertEqual(ss.load_last_full_scan(self.state), TODAY)

    def test_full_scan_with_offline_tool_does_not_update_state(self):
        before = ss.load_last_full_scan(self.state)
        offline = (2, "", "ConnectionError: Max retries exceeded")
        run_scan(self.root, FakeRunner(pip_audit=offline), force_full=True)
        self.assertEqual(ss.load_last_full_scan(self.state), before)

    def test_stale_baseline_hint_only_in_full_mode(self):
        baseline = {"findings": [{"fingerprint": "semgrep:fpgone", "rule": "r", "reason": "r", "expires": "2027-01-01"}]}
        (self.root / ".agents" / "security_baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
        _, diff_out = self.scan_diff(FakeRunner(git_ok=True, git_diff=["app/server.py"]))
        self.assertNotIn("可移除", diff_out)
        _, full_out = run_scan(self.root, FakeRunner(), force_full=True)
        self.assertIn("基準項目已無對應發現，可移除: semgrep:fpgone", full_out)


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
