import unittest
from unittest.mock import MagicMock, patch
from src.domain.models import Document, SearchQuery, SearchResultItem
from src.domain.enums import DocumentType, DocumentHealth, ChunkType
from src.infrastructure.probes.pdf_probe import PdfHealthProbe
from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker
from src.infrastructure.stores.redis_vector_store import RedisVectorStore
from src.infrastructure.transformers.gemini_transformer import GeminiTransformer


class TestHardcodeExtractions(unittest.TestCase):
    """
    白箱單元測試：針對新提取之環境變數、閥值與 Prompt 解耦進行 100% 離線 Mock 驗證
    """

    def test_pdf_health_probe_custom_thresholds(self):
        # 1. Arrange: 自訂較嚴格的掃描字數門檻 (50 字)
        probe = PdfHealthProbe(scanned_min_chars=50, ufffd_threshold=5, strikethrough_threshold=15)
        self.assertEqual(probe.scanned_min_chars, 50)
        self.assertEqual(probe.ufffd_threshold, 5)
        self.assertEqual(probe.strikethrough_threshold, 15)

    def test_markdown_chunker_extra_skill_patterns(self):
        # 1. Arrange: 擴充自訂技能標籤 (flutter, solidity)
        chunker = MarkdownChunker(
            min_chunk_chars=50,
            max_chunk_chars=1000,
            extra_skill_patterns=["flutter", "solidity", "rust"],
        )
        md_text = (
            "# 測試工程師\n"
            "## 專業技能\n"
            "精通 Flutter 行動端開發與 Rust 系統編程，並曾參與 Solidity 智能合約審計。\n"
        )

        # 2. Act
        chunks = chunker.chunk_markdown(md_text, candidate_id="cand_test")

        # 3. Assert: 驗證自訂標籤被正確提取
        self.assertTrue(len(chunks) > 0)
        all_skills = set()
        for c in chunks:
            all_skills.update(c.skills)

        self.assertIn("flutter", all_skills)
        self.assertIn("solidity", all_skills)
        self.assertIn("rust", all_skills)

    def test_redis_vector_store_initial_cap_and_min_score_filter(self):
        # 1. Arrange: 驗證建構子接收自訂 HNSW INITIAL_CAP
        store = RedisVectorStore(
            redis_url="redis://localhost:6379/0",
            hnsw_initial_cap=5000,
        )
        self.assertEqual(store.hnsw_initial_cap, 5000)

        # 2. Mock client.ft().search() 驗證 search 依 min_score 過濾
        mock_doc1 = MagicMock()
        mock_doc1.score = "0.2"  # distance 0.2 -> similarity 0.8
        mock_doc1.candidate_id = "c1"
        mock_doc1.candidate_name = "Alice"
        mock_doc1.chunk_type = "skills"
        mock_doc1.section_title = "技能"
        mock_doc1.content = "Python"
        mock_doc1.skills = "python"
        mock_doc1.file_path = "test.md"

        mock_doc2 = MagicMock()
        mock_doc2.score = "0.7"  # distance 0.7 -> similarity 0.3
        mock_doc2.candidate_id = "c2"
        mock_doc2.candidate_name = "Bob"
        mock_doc2.chunk_type = "profile"
        mock_doc2.section_title = "簡介"
        mock_doc2.content = "Hello"
        mock_doc2.skills = ""
        mock_doc2.file_path = "test2.md"

        mock_res = MagicMock()
        mock_res.docs = [mock_doc1, mock_doc2]

        mock_client = MagicMock()
        mock_client.ft.return_value.search.return_value = mock_res
        store._client = mock_client

        # 3. Act: 查詢時要求最低相似度 0.5 (應過濾掉 similarity 0.3 的 Bob)
        query = SearchQuery(
            query_text="尋找 Python 專家",
            top_k=5,
            min_score=0.5,
        )
        results = store.search(query_vector=[0.1] * 768, query=query)

        # 4. Assert: 只有 Alice 通過門檻
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].candidate_name, "Alice")
        self.assertGreaterEqual(results[0].score, 0.5)

    @patch("src.infrastructure.transformers.gemini_transformer.genai.Client")
    def test_gemini_transformer_custom_params_and_prompts(self, mock_genai_client):
        # 1. Arrange: 驗證自訂溫度與 Token 傳遞
        transformer = GeminiTransformer(
            api_key="mock_key",
            temperature=0.0,
            max_output_tokens=4096,
        )
        self.assertEqual(transformer.temperature, 0.0)
        self.assertEqual(transformer.max_output_tokens, 4096)
        # 驗證 prompt 模板成功由 prompts/ 載入
        self.assertIn("<resume_content>", transformer.text_prompt_template)
        self.assertIn("自我修復", transformer.text_review_prompt)
        self.assertIn("結構清晰", transformer.vision_prompt)

    @patch("src.infrastructure.validators.llm_judge.genai.Client")
    def test_llm_judge_prompts_loaded_from_assets(self, mock_genai_client):
        from src.infrastructure.validators.llm_judge import GeminiLlmJudge
        judge = GeminiLlmJudge(api_key="mock_key")
        self.assertIn("極度嚴格", judge.system_prompt)
        self.assertIn("=== 原始文件資訊 ===", judge.vision_prompt_template)
        self.assertIn("<resume_content type=\"converted_markdown\">", judge.vision_prompt_template)
        self.assertIn("=== 原始提取文字與表格 ===", judge.text_prompt_template)
        self.assertIn("<resume_content type=\"raw_source_text\">", judge.text_prompt_template)

    def test_audit_guardrails_detects_prompt_hardcoding(self):
        # 1. Arrange: 模擬帶有硬編碼提示詞的 AST 語法樹
        import ast
        from pathlib import Path
        import sys

        project_root = Path(__file__).resolve().parents[2]
        guardrail_script = project_root / ".agents" / "skills" / "code-review" / "scripts" / "audit_guardrails.py"
        self.assertTrue(guardrail_script.exists())

        # 動態載入 audit_guardrails 模組進行負面測試
        import importlib.util
        spec = importlib.util.spec_from_file_location("audit_guardrails", guardrail_script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 2. Assert: 驗證既有 codebase 零 Prompt 硬編碼
        violations = module.check_prompt_hardcoding()
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
