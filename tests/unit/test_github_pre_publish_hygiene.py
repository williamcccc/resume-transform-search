import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


class TestGitHubPrePublishHygiene(unittest.TestCase):
    """
    白箱單元測試：驗證 GitHub 開源/上庫前之版控邊界 (.gitignore)、
    環境變數範本 (.env.example) 同步性、跨平台路徑解耦與提示詞純淨度。
    """

    def setUp(self):
        self.root_dir = Path(__file__).resolve().parents[2]
        self.ignore_dirs = {
            ".git",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            "data",
            "resume",
            "resumes",
            "output",
            "output_md",
            "markdown_out",
            "markdown_output",
            "quarantine",
            "scorecards",
            "logs",
            "scratch",
            ".vscode",
        }

    def test_gitignore_covers_sensitive_and_runtime_paths(self):
        # 1. Arrange
        gitignore_path = self.root_dir / ".gitignore"
        self.assertTrue(gitignore_path.exists(), ".gitignore 檔案必須存在")

        # 2. Act
        content = gitignore_path.read_text(encoding="utf-8")
        lines = {line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")}

        # 3. Assert
        required_entries = [
            ".env",
            "data/",
            "resume/",
            "resumes/",
            "output/",
            "output_md/",
            "markdown_out/",
            "markdown_output/",
            "quarantine/",
            "scorecards/",
            "logs/",
            "dump.rdb",
            "appendonlydir/",
        ]
        for entry in required_entries:
            self.assertIn(entry, lines, f".gitignore 漏列關鍵保護項目: {entry}")

    def test_env_example_covers_all_app_config_variables_and_has_no_real_secrets(self):
        # 1. Arrange
        config_path = self.root_dir / "src" / "infrastructure" / "config.py"
        env_example_path = self.root_dir / ".env.example"
        self.assertTrue(config_path.exists())
        self.assertTrue(env_example_path.exists())

        # 2. Act
        config_text = config_path.read_text(encoding="utf-8")
        env_example_text = env_example_path.read_text(encoding="utf-8")

        config_env_keys = set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z0-9_]+)["\']', config_text))
        example_env_keys = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", env_example_text, re.MULTILINE))

        # 3. Assert: 所有 AppConfig 讀取的環境變數都必須在 .env.example 中有記載
        missing_in_example = config_env_keys - example_env_keys
        self.assertEqual(
            missing_in_example,
            set(),
            f"AppConfig 中定義的環境變數未同步至 .env.example: {missing_in_example}",
        )

        # 確保 .env.example 不含真實 API 金鑰
        secret_pattern = re.compile(r"(?:AQ\.[a-zA-Z0-9_-]{20,}|AIzaSy[a-zA-Z0-9_-]{20,})")
        self.assertIsNone(secret_pattern.search(env_example_text), ".env.example 嚴禁包含真實 API 金鑰")

    def test_no_hardcoded_workspace_paths_or_secrets_in_repo_files(self):
        # 1. Arrange
        workspace_pattern = re.compile(r"[cC]:[/\\]+" + "Python" + "Workspace")
        secret_pattern = re.compile(r"(?:AQ\.[a-zA-Z0-9_-]{20,}|AIzaSy[a-zA-Z0-9_-]{20,})")
        violations = []

        # 2. Act
        for file_path in self.root_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel_parts = set(file_path.relative_to(self.root_dir).parts)
            if rel_parts & self.ignore_dirs or file_path.name == ".env":
                continue
            if file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".doc"}:
                continue

            try:
                text = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            rel_str = str(file_path.relative_to(self.root_dir))
            if workspace_pattern.search(text):
                violations.append(f"[Hardcoded Workspace Path] {rel_str}")
            if secret_pattern.search(text):
                violations.append(f"[Leaked Secret Key] {rel_str}")

        # 3. Assert
        self.assertEqual(violations, [], f"偵測到殘留本機絕對路徑或機密金鑰: {violations}")

    def _load_audit_guardrails(self):
        import importlib.util

        guardrail_script = (
            self.root_dir / ".agents" / "skills" / "code-review" / "scripts" / "audit_guardrails.py"
        )
        spec = importlib.util.spec_from_file_location("audit_guardrails", guardrail_script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_privacy_marker_scanner_detects_masked_names_and_personal_filenames(self):
        # 1. Arrange: 只在記憶體組合合成標記，不在測試原始碼寫入遮蔽識別值。
        scanner = self._load_audit_guardrails()
        masked_text = "\u5019\u9078" + chr(0x25CB) + "\u4eba"
        personal_filename = "Synthetic" + "-CV.pdf"
        quoted_personal_filename = "`" + "Synthetic" + "-CV" + "`"
        personal_resume_path = "resume/" + "Synthetic" + ".md"
        sensitive_file_path = "resume/" + "Synthetic" + "-CV.pdf"

        # 2. Act
        masked_markers = scanner.find_privacy_markers(masked_text)
        filename_markers = scanner.find_privacy_markers(personal_filename)
        quoted_filename_markers = scanner.find_privacy_markers(quoted_personal_filename)
        resume_path_markers = scanner.find_privacy_markers(personal_resume_path)
        sensitive_path_markers = scanner.find_privacy_markers(sensitive_file_path)
        safe_sample_markers = scanner.find_privacy_markers("sample_resume.md")
        safe_resume_path_markers = scanner.find_privacy_markers("resume/sample_resume.md")

        # 3. Assert
        self.assertIn("masked_cjk_identifier", masked_markers)
        self.assertIn("personal_resume_filename", filename_markers)
        self.assertIn("personal_resume_filename", quoted_filename_markers)
        self.assertIn("personal_resume_filename", resume_path_markers)
        self.assertEqual(scanner.safe_path_for_report(sensitive_file_path, sensitive_path_markers), "[redacted-path]")
        self.assertEqual(safe_sample_markers, [])
        self.assertEqual(safe_resume_path_markers, [])

    def test_privacy_marker_scanner_detects_contact_formats_without_echoing_values(self):
        # 1. Arrange: 使用無效測試網域與動態組合的合成數字。
        scanner = self._load_audit_guardrails()
        safe_email = "person@example.com"
        synthetic_phone = "09" + "0" * 8
        synthetic_landline = "02" + "0" * 7
        synthetic_id = "A" + "1" + "0" * 8

        # 2. Act
        safe_email_markers = scanner.find_privacy_markers(safe_email)
        phone_markers = scanner.find_privacy_markers(synthetic_phone)
        landline_markers = scanner.find_privacy_markers(synthetic_landline)
        id_markers = scanner.find_privacy_markers(synthetic_id)

        # 3. Assert
        self.assertEqual(safe_email_markers, [])
        self.assertIn("phone_number", phone_markers)
        self.assertIn("phone_number", landline_markers)
        self.assertIn("taiwan_id_number", id_markers)

    def test_prompts_and_code_free_of_real_candidate_names_and_company_examples(self):
        # 1. Arrange: 複用審查防線，錯誤只回報檔案路徑與命中類別。
        scanner = self._load_audit_guardrails()
        violations = []

        # 2. Act
        for file_path in self.root_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel_parts = set(file_path.relative_to(self.root_dir).parts)
            if rel_parts & self.ignore_dirs or file_path.name == ".env":
                continue
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            markers = set(scanner.find_privacy_markers(rel_path))
            if file_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".doc"}:
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue
                markers.update(scanner.find_privacy_markers(text))
            violations.extend(f"{rel_path}: {marker}" for marker in sorted(markers))

        # 3. Assert
        self.assertEqual(violations, [], f"偵測到未脫敏之真實人名或企業名稱: {violations}")

    def test_repository_markdown_links_resolve(self):
        # 1. Arrange
        link_pattern = re.compile(r"\]\(([^)]+)\)")
        fence_pattern = re.compile(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$")
        broken_links = []

        # 2. Act
        for file_path in self.root_dir.rglob("*.md"):
            rel_parts = set(file_path.relative_to(self.root_dir).parts)
            if rel_parts & self.ignore_dirs:
                continue
            try:
                markdown = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            markdown = fence_pattern.sub("", markdown)
            for raw_target in link_pattern.findall(markdown):
                target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme in {"http", "https", "mailto", "data"} or target.startswith("#"):
                    continue
                if parsed.scheme:
                    broken_links.append(file_path.relative_to(self.root_dir).as_posix())
                    continue
                relative_target = unquote(parsed.path).split("#", 1)[0]
                if not relative_target:
                    continue
                if relative_target.startswith("/"):
                    destination = self.root_dir / relative_target.lstrip("/")
                else:
                    destination = file_path.parent / relative_target
                try:
                    destination.resolve().relative_to(self.root_dir.resolve())
                except ValueError:
                    broken_links.append(file_path.relative_to(self.root_dir).as_posix())
                    continue
                if not destination.resolve().exists():
                    broken_links.append(file_path.relative_to(self.root_dir).as_posix())

        # 3. Assert: 不將可能含敏感內容的連結目標寫入測試錯誤訊息。
        self.assertEqual(broken_links, [], f"Markdown 文件仍有斷鏈，參照文件數: {len(broken_links)}")

    def test_audit_guardrails_git_hygiene_check_passes(self):
        # 1. Arrange: 動態載入 audit_guardrails 驗證新增的第 7 道防線
        module = self._load_audit_guardrails()

        # 2. Act
        violations = module.check_git_hygiene_and_pii_guardrails()

        # 3. Assert
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
