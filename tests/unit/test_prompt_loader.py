import unittest
from src.infrastructure.prompts import load_prompt, PROMPTS_DIR


class TestPromptLoader(unittest.TestCase):
    """
    測試 Prompt Engineering 提示詞獨立檔案載入器
    100% 離線白箱驗證，確保 Prompt 檔案存在且內容完整
    """

    def test_load_existing_prompts(self):
        # 1. 驗證自我審查提示詞載入
        review_prompt = load_prompt("self_review.md")
        self.assertIn("極度嚴格的履歷品質稽核專家", review_prompt)
        self.assertIn("5 大維度", review_prompt)

        # 2. 驗證多模態視覺初稿提示詞載入
        vision_prompt = load_prompt("vision_convert.md")
        self.assertIn("專業的文件與履歷結構化解析專家", vision_prompt)
        self.assertIn("嚴禁輸出「## Page 1」", vision_prompt)

        # 3. 驗證獨立評判員提示詞載入
        judge_prompt = load_prompt("judge_system.md")
        self.assertIn("LLM-as-a-Judge", judge_prompt)
        self.assertIn("completeness_score", judge_prompt)
        self.assertIn("fidelity_score", judge_prompt)
        self.assertIn("Prompt Injection 防禦", judge_prompt)

        # 4. 驗證純文字轉換提示詞載入
        text_convert_prompt = load_prompt("text_convert.md")
        self.assertIn("<resume_content>", text_convert_prompt)
        self.assertIn("{doc_type}", text_convert_prompt)
        self.assertIn("{text}", text_convert_prompt)

        # 5. 驗證純文字自我審查提示詞載入
        text_review_prompt = load_prompt("text_review.md")
        self.assertIn("自我修復後的", text_review_prompt)

        # 6. 驗證獨立評判員視覺模板載入
        judge_vision = load_prompt("judge_vision_prompt.md")
        self.assertIn("=== 原始文件資訊 ===", judge_vision)
        self.assertIn("<resume_content type=\"converted_markdown\">", judge_vision)

        # 7. 驗證獨立評判員文字模板載入
        judge_text = load_prompt("judge_text_prompt.md")
        self.assertIn("=== 原始提取文字與表格 ===", judge_text)
        self.assertIn("<resume_content type=\"raw_source_text\">", judge_text)

    def test_load_non_existent_prompt_with_fallback(self):
        # 測試載入不存在之 prompt 檔案時，能優雅回退至 fallback_text
        content = load_prompt("non_existent_file.md", fallback_text="DEFAULT_FALLBACK")
        self.assertEqual(content, "DEFAULT_FALLBACK")

    def test_load_non_existent_prompt_without_fallback_raises(self):
        # 測試未提供 fallback 時拋出 FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            load_prompt("definitely_not_found.md")


if __name__ == "__main__":
    unittest.main()
