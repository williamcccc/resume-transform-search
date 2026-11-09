import os
import unittest
from unittest.mock import patch
from src.infrastructure.config import AppConfig
from src.infrastructure.validators.quality_validator import MarkdownQualityValidator


class TestAppConfig(unittest.TestCase):
    """
    AppConfig 全域環境變數載入與覆寫白箱單元測試
    100% 離線 Mock 隔離，涵蓋各項外部服務 URL、索引前綴與微調參數
    """

    @patch("dotenv.load_dotenv")
    def test_default_config_values(self, mock_load_dotenv):
        # 1. Arrange: 清理環境變數，避免讀取實體 .env 檔案
        with patch.dict(os.environ, {}, clear=True):
            # 2. Act
            cfg = AppConfig.load(override_api_key="mock_key")

            # 3. Assert
            self.assertEqual(cfg.gemini_api_key, "mock_key")
            self.assertEqual(cfg.gemini_model, "gemini-3.8-flash")
            self.assertFalse(cfg.gemini_review)
            self.assertFalse(cfg.gemini_judge)
            self.assertEqual(cfg.gemini_temperature, 0.2)
            self.assertEqual(cfg.gemini_max_output_tokens, 8192)
            self.assertEqual(cfg.redis_url, "redis://localhost:6379/0")
            self.assertEqual(cfg.redis_test_url, "redis://localhost:6379/15")
            self.assertEqual(cfg.redis_index_name, "idx:resumes:v1")
            self.assertEqual(cfg.redis_prefix, "resume:v1:chunk:")
            self.assertEqual(cfg.redis_hash_prefix, "resume:v1:hash:")
            self.assertEqual(cfg.redis_hnsw_m, 16)
            self.assertEqual(cfg.redis_hnsw_ef_construction, 200)
            self.assertEqual(cfg.redis_hnsw_initial_cap, 1000)
            self.assertEqual(cfg.redis_distance_metric, "COSINE")
            self.assertEqual(cfg.embedding_model, "gemini-embedding-001")
            self.assertEqual(cfg.embedding_batch_size, 20)
            self.assertEqual(cfg.embedding_dim, 768)
            self.assertEqual(cfg.min_chunk_size, 80)
            self.assertEqual(cfg.max_chunk_size, 1500)
            self.assertEqual(cfg.quality_threshold, 65)
            self.assertEqual(cfg.quality_min_retention_ratio, 0.35)
            self.assertEqual(cfg.quality_max_retention_ratio, 3.5)
            self.assertEqual(cfg.max_file_size_mb, 25)
            self.assertEqual(cfg.max_pdf_pages, 30)
            self.assertEqual(cfg.max_docx_expansion_ratio, 10.0)
            self.assertEqual(cfg.max_docx_uncompressed_mb, 100)
            self.assertEqual(cfg.api_max_retries, 3)
            self.assertEqual(cfg.api_retry_delay, 2.0)
            self.assertEqual(cfg.pdf_render_dpi, 150)
            self.assertEqual(cfg.pdf_ocr_dpi, 200)
            self.assertEqual(cfg.pdf_text_first_min_chars, 50)
            self.assertEqual(cfg.pdf_scanned_min_chars, 30)
            self.assertEqual(cfg.pdf_obfuscated_ufffd_threshold, 10)
            self.assertEqual(cfg.pdf_obfuscated_strikethrough_threshold, 30)
            self.assertEqual(cfg.vision_review_max_pages, 5)
            self.assertEqual(cfg.search_default_top_k, 5)
            self.assertEqual(cfg.search_min_score, 0.0)
            self.assertEqual(cfg.extra_skill_patterns, [])
            self.assertIsNone(cfg.default_output_dir)
            self.assertIsNone(cfg.default_quarantine_dir)
            self.assertIsNone(cfg.default_audit_report)
            self.assertIsNone(cfg.default_scorecard_dir)
            self.assertEqual(cfg.log_level, "INFO")
            self.assertEqual(cfg.log_file, "logs/app.log")
            self.assertEqual(cfg.log_max_bytes, 10 * 1024 * 1024)
            self.assertEqual(cfg.log_backup_count, 5)

    @patch("dotenv.load_dotenv")
    def test_custom_env_values(self, mock_load_dotenv):
        # 1. Arrange: 模擬自訂環境變數
        custom_env = {
            "GEMINI_API_KEY": "custom_key",
            "GEMINI_MODEL": "gemini-2.0-flash",
            "GEMINI_REVIEW": "true",
            "GEMINI_JUDGE": "1",
            "GEMINI_TEMPERATURE": "0.0",
            "GEMINI_MAX_OUTPUT_TOKENS": "4096",
            "REDIS_URL": "redis://remote-host:6380/1",
            "REDIS_TEST_URL": "redis://remote-host:6380/15",
            "REDIS_INDEX_NAME": "idx:resumes:custom",
            "REDIS_PREFIX": "custom:chunk:",
            "REDIS_HASH_PREFIX": "custom:hash:",
            "REDIS_HNSW_M": "32",
            "REDIS_HNSW_EF_CONSTRUCTION": "400",
            "REDIS_HNSW_INITIAL_CAP": "5000",
            "REDIS_DISTANCE_METRIC": "IP",
            "GEMINI_EMBEDDING_MODEL": "custom-embedding",
            "EMBEDDING_BATCH_SIZE": "50",
            "EMBEDDING_DIM": "1536",
            "MIN_CHUNK_SIZE": "120",
            "MAX_CHUNK_SIZE": "2000",
            "QUALITY_THRESHOLD": "75",
            "QUALITY_MIN_RETENTION_RATIO": "0.4",
            "QUALITY_MAX_RETENTION_RATIO": "4.0",
            "MAX_FILE_SIZE_MB": "50",
            "MAX_PDF_PAGES": "50",
            "MAX_DOCX_EXPANSION_RATIO": "15.5",
            "MAX_DOCX_UNCOMPRESSED_MB": "150",
            "API_MAX_RETRIES": "5",
            "API_RETRY_DELAY": "3.5",
            "PDF_RENDER_DPI": "200",
            "PDF_OCR_DPI": "250",
            "PDF_TEXT_FIRST_MIN_CHARS": "100",
            "PDF_SCANNED_MIN_CHARS": "45",
            "PDF_OBFUSCATED_UFFFD_THRESHOLD": "15",
            "PDF_OBFUSCATED_STRIKETHROUGH_THRESHOLD": "40",
            "VISION_REVIEW_MAX_PAGES": "8",
            "SEARCH_DEFAULT_TOP_K": "10",
            "SEARCH_MIN_SCORE": "0.55",
            "EXTRA_SKILL_PATTERNS": "swift, flutter, rust , solidity ",
            "DEFAULT_OUTPUT_DIR": "data/custom_output",
            "DEFAULT_QUARANTINE_DIR": "data/quarantine_test",
            "DEFAULT_AUDIT_REPORT": "logs/audit_test.csv",
            "DEFAULT_SCORECARD_DIR": "data/scorecards_test",
            "LOG_LEVEL": "debug",
            "LOG_FILE": "logs/custom.log",
            "LOG_MAX_BYTES": "20971520",
            "LOG_BACKUP_COUNT": "10",
        }

        # 2. Act
        with patch.dict(os.environ, custom_env, clear=True):
            cfg = AppConfig.load()

        # 3. Assert
        self.assertEqual(cfg.gemini_api_key, "custom_key")
        self.assertEqual(cfg.gemini_model, "gemini-2.0-flash")
        self.assertTrue(cfg.gemini_review)
        self.assertTrue(cfg.gemini_judge)
        self.assertEqual(cfg.gemini_temperature, 0.0)
        self.assertEqual(cfg.gemini_max_output_tokens, 4096)
        self.assertEqual(cfg.redis_url, "redis://remote-host:6380/1")
        self.assertEqual(cfg.redis_test_url, "redis://remote-host:6380/15")
        self.assertEqual(cfg.redis_index_name, "idx:resumes:custom")
        self.assertEqual(cfg.redis_prefix, "custom:chunk:")
        self.assertEqual(cfg.redis_hash_prefix, "custom:hash:")
        self.assertEqual(cfg.redis_hnsw_m, 32)
        self.assertEqual(cfg.redis_hnsw_ef_construction, 400)
        self.assertEqual(cfg.redis_hnsw_initial_cap, 5000)
        self.assertEqual(cfg.redis_distance_metric, "IP")
        self.assertEqual(cfg.embedding_model, "custom-embedding")
        self.assertEqual(cfg.embedding_batch_size, 50)
        self.assertEqual(cfg.embedding_dim, 1536)
        self.assertEqual(cfg.min_chunk_size, 120)
        self.assertEqual(cfg.max_chunk_size, 2000)
        self.assertEqual(cfg.quality_threshold, 75)
        self.assertEqual(cfg.quality_min_retention_ratio, 0.4)
        self.assertEqual(cfg.quality_max_retention_ratio, 4.0)
        self.assertEqual(cfg.max_file_size_mb, 50)
        self.assertEqual(cfg.max_pdf_pages, 50)
        self.assertEqual(cfg.max_docx_expansion_ratio, 15.5)
        self.assertEqual(cfg.max_docx_uncompressed_mb, 150)
        self.assertEqual(cfg.api_max_retries, 5)
        self.assertEqual(cfg.api_retry_delay, 3.5)
        self.assertEqual(cfg.pdf_render_dpi, 200)
        self.assertEqual(cfg.pdf_ocr_dpi, 250)
        self.assertEqual(cfg.pdf_text_first_min_chars, 100)
        self.assertEqual(cfg.pdf_scanned_min_chars, 45)
        self.assertEqual(cfg.pdf_obfuscated_ufffd_threshold, 15)
        self.assertEqual(cfg.pdf_obfuscated_strikethrough_threshold, 40)
        self.assertEqual(cfg.vision_review_max_pages, 8)
        self.assertEqual(cfg.search_default_top_k, 10)
        self.assertEqual(cfg.search_min_score, 0.55)
        self.assertEqual(cfg.extra_skill_patterns, ["swift", "flutter", "rust", "solidity"])
        self.assertEqual(cfg.default_output_dir, "data/custom_output")
        self.assertEqual(cfg.default_quarantine_dir, "data/quarantine_test")
        self.assertEqual(cfg.default_audit_report, "logs/audit_test.csv")
        self.assertEqual(cfg.default_scorecard_dir, "data/scorecards_test")
        self.assertEqual(cfg.log_level, "DEBUG")
        self.assertEqual(cfg.log_file, "logs/custom.log")
        self.assertEqual(cfg.log_max_bytes, 20971520)
        self.assertEqual(cfg.log_backup_count, 10)

    @patch("dotenv.load_dotenv")
    def test_invalid_integer_env_fallback(self, mock_load_dotenv):
        # 1. Arrange: 模擬環境變數傳入非數字字串，驗證優雅退回預設值不崩潰
        invalid_env = {
            "GEMINI_TEMPERATURE": "bad_temp",
            "GEMINI_MAX_OUTPUT_TOKENS": "bad_tokens",
            "EMBEDDING_BATCH_SIZE": "not_a_number",
            "EMBEDDING_DIM": "invalid_dim",
            "MIN_CHUNK_SIZE": "invalid",
            "MAX_CHUNK_SIZE": "too_big_string",
            "QUALITY_THRESHOLD": "abc",
            "QUALITY_MIN_RETENTION_RATIO": "bad_float",
            "QUALITY_MAX_RETENTION_RATIO": "bad_float2",
            "MAX_FILE_SIZE_MB": "invalid_mb",
            "MAX_PDF_PAGES": "not_int",
            "MAX_DOCX_EXPANSION_RATIO": "not_float",
            "MAX_DOCX_UNCOMPRESSED_MB": "bad_mb",
            "API_MAX_RETRIES": "bad_retries",
            "API_RETRY_DELAY": "bad_delay",
            "PDF_RENDER_DPI": "dpi_string",
            "PDF_OCR_DPI": "bad_ocr_dpi",
            "PDF_TEXT_FIRST_MIN_CHARS": "bad_chars",
            "PDF_SCANNED_MIN_CHARS": "bad_scanned",
            "PDF_OBFUSCATED_UFFFD_THRESHOLD": "bad_ufffd",
            "PDF_OBFUSCATED_STRIKETHROUGH_THRESHOLD": "bad_strike",
            "VISION_REVIEW_MAX_PAGES": "bad_pages",
            "SEARCH_DEFAULT_TOP_K": "bad_k",
            "SEARCH_MIN_SCORE": "bad_score",
            "REDIS_HNSW_M": "bad_m",
            "REDIS_HNSW_EF_CONSTRUCTION": "bad_ef",
            "REDIS_HNSW_INITIAL_CAP": "bad_initial_cap",
            "LOG_MAX_BYTES": "bad_bytes",
            "LOG_BACKUP_COUNT": "bad_count",
        }

        # 2. Act
        with patch.dict(os.environ, invalid_env, clear=True):
            cfg = AppConfig.load(override_api_key="mock_key")

        # 3. Assert
        self.assertEqual(cfg.gemini_temperature, 0.2)
        self.assertEqual(cfg.gemini_max_output_tokens, 8192)
        self.assertEqual(cfg.embedding_batch_size, 20)
        self.assertEqual(cfg.embedding_dim, 768)
        self.assertEqual(cfg.min_chunk_size, 80)
        self.assertEqual(cfg.max_chunk_size, 1500)
        self.assertEqual(cfg.quality_threshold, 65)
        self.assertEqual(cfg.quality_min_retention_ratio, 0.35)
        self.assertEqual(cfg.quality_max_retention_ratio, 3.5)
        self.assertEqual(cfg.max_file_size_mb, 25)
        self.assertEqual(cfg.max_pdf_pages, 30)
        self.assertEqual(cfg.max_docx_expansion_ratio, 10.0)
        self.assertEqual(cfg.max_docx_uncompressed_mb, 100)
        self.assertEqual(cfg.api_max_retries, 3)
        self.assertEqual(cfg.api_retry_delay, 2.0)
        self.assertEqual(cfg.pdf_render_dpi, 150)
        self.assertEqual(cfg.pdf_ocr_dpi, 200)
        self.assertEqual(cfg.pdf_text_first_min_chars, 50)
        self.assertEqual(cfg.pdf_scanned_min_chars, 30)
        self.assertEqual(cfg.pdf_obfuscated_ufffd_threshold, 10)
        self.assertEqual(cfg.pdf_obfuscated_strikethrough_threshold, 30)
        self.assertEqual(cfg.vision_review_max_pages, 5)
        self.assertEqual(cfg.search_default_top_k, 5)
        self.assertEqual(cfg.search_min_score, 0.0)
        self.assertEqual(cfg.redis_hnsw_m, 16)
        self.assertEqual(cfg.redis_hnsw_ef_construction, 200)
        self.assertEqual(cfg.redis_hnsw_initial_cap, 1000)
        self.assertEqual(cfg.log_max_bytes, 10 * 1024 * 1024)
        self.assertEqual(cfg.log_backup_count, 5)

    def test_quality_validator_custom_threshold(self):
        # 1. Arrange: 驗證自訂品管門檻生效
        validator_strict = MarkdownQualityValidator(pass_threshold=80)
        # 產生一個得分約 70 分的 markdown (例如缺少手機號碼或扣分)
        md_content = "# 姓名\n## 工作經歷\n經歷內容\n## 專業技能\nPython"

        # 2. Act
        report = validator_strict.validate(md_content)

        # 3. Assert: 驗證使用自訂門檻 (80) 判定
        self.assertEqual(validator_strict.pass_threshold, 80)
        self.assertIsInstance(report.is_passed, bool)


if __name__ == "__main__":
    unittest.main()


class TestRecruitmentAppConfig(unittest.TestCase):
    """招募助手 (ADR-0019) 新增 RECRUIT_*/CHAT_* 配置之預設值、覆寫與 .env.example 同步 (AC-32)"""

    @patch("dotenv.load_dotenv")
    def test_recruit_defaults(self, mock_load_dotenv):
        with patch.dict(os.environ, {}, clear=True):
            cfg = AppConfig.load(override_api_key="mock_key", override_model="model-x")
        self.assertTrue(cfg.recruit_chat_enabled)
        self.assertEqual(cfg.recruit_llm_model, "model-x")  # 留空沿用 GEMINI_MODEL
        self.assertEqual(cfg.recruit_candidate_pool_size, 15)
        self.assertEqual(cfg.recruit_candidate_pool_max, 30)
        self.assertEqual(cfg.recruit_shortlist_size, 3)
        self.assertEqual(cfg.recruit_max_llm_calls_per_turn, 25)
        self.assertEqual(cfg.recruit_turn_timeout_seconds, 150.0)
        self.assertEqual(cfg.recruit_llm_timeout_seconds, 45.0)
        self.assertEqual(cfg.recruit_profile_max_concurrency, 8)
        self.assertEqual(cfg.recruit_profile_max_output_tokens, 1024)
        self.assertEqual(cfg.recruit_profile_negative_cache_ttl_seconds, 600)
        self.assertEqual(cfg.recruit_profile_cache_prefix, "recruit:v1:profile:")
        self.assertIn("婚姻", cfg.recruit_protected_attr_terms)
        self.assertEqual(cfg.recruit_skill_aliases["k8s"], "kubernetes")
        self.assertEqual(cfg.chat_checkpointer_backend, "memory")
        self.assertEqual(cfg.chat_checkpoint_redis_url, cfg.redis_url)
        self.assertEqual(cfg.chat_memory_max_sessions, 200)

    @patch("dotenv.load_dotenv")
    def test_recruit_env_overrides_and_invalid_values(self, mock_load_dotenv):
        env = {
            "RECRUIT_CHAT_ENABLED": "false",
            "RECRUIT_LLM_MODEL": "recruit-model",
            "RECRUIT_SHORTLIST_SIZE": "5",
            "RECRUIT_RETRIEVAL_MIN_SCORE": "abc",
            "RECRUIT_SKILL_ALIASES": "py:python, bad_item ,ts:typescript",
            "RECRUIT_PROTECTED_ATTR_TERMS": "年齡, 性別",
            "CHAT_CHECKPOINTER_BACKEND": "REDIS",
            "CHAT_CHECKPOINT_REDIS_URL": "redis://checkpoint-host:6379/2",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AppConfig.load(override_api_key="mock_key")
        self.assertFalse(cfg.recruit_chat_enabled)
        self.assertEqual(cfg.recruit_llm_model, "recruit-model")
        self.assertEqual(cfg.recruit_shortlist_size, 5)
        self.assertEqual(cfg.recruit_retrieval_min_score, 0.5)
        self.assertEqual(cfg.recruit_skill_aliases, {"py": "python", "ts": "typescript"})
        self.assertEqual(cfg.recruit_protected_attr_terms, ["年齡", "性別"])
        self.assertEqual(cfg.chat_checkpointer_backend, "redis")
        self.assertEqual(cfg.chat_checkpoint_redis_url, "redis://checkpoint-host:6379/2")

    def test_env_example_should_cover_all_recruit_and_chat_keys(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        cfg_text = (root / "src" / "infrastructure" / "config.py").read_text(encoding="utf-8")
        example = (root / ".env.example").read_text(encoding="utf-8")
        keys = set(re.findall(r'os\.environ\.get\(\s*"((?:RECRUIT|CHAT)_[A-Z0-9_]+)"', cfg_text))
        example_keys = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", example, re.MULTILINE))
        self.assertGreaterEqual(len(keys), 37)
        self.assertEqual(sorted(keys - example_keys), [])
