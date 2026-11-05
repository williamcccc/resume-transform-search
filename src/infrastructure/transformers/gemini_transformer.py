from typing import List, Optional
from google import genai
from google.genai import types

from src.domain.models import Document, ConvertedMarkdown
from src.domain.enums import DocumentHealth
from src.domain.interfaces import IMarkdownTransformer
from src.infrastructure.prompts import load_prompt
from src.infrastructure.transformers.utils import clean_markdown_response, retry_call

# 從獨立檔案載入 Prompt Engineering 提示詞 (便於 Git 版控與獨立優化)
SELF_REVIEW_PROMPT = load_prompt("self_review.md")
TEXT_CONVERT_TEMPLATE = load_prompt("text_convert.md")
TEXT_REVIEW_PROMPT = load_prompt("text_review.md")
VISION_CONVERT_PROMPT = load_prompt("vision_convert.md")


class GeminiTransformer(IMarkdownTransformer):
    """
    Google Gemini 多模態與文字語意轉換器
    支援單次極速模式與兩階段 Chat 自我審查與修復 (Self-Refinement)
    """
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.8-flash",
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        review_prompt: Optional[str] = None,
        vision_prompt: Optional[str] = None,
        text_prompt_template: Optional[str] = None,
        text_review_prompt: Optional[str] = None,
        vision_review_max_pages: int = 5,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.review_prompt = review_prompt or SELF_REVIEW_PROMPT
        self.vision_prompt = vision_prompt or VISION_CONVERT_PROMPT
        self.text_prompt_template = text_prompt_template or TEXT_CONVERT_TEMPLATE
        self.text_review_prompt = text_review_prompt or TEXT_REVIEW_PROMPT
        self.vision_review_max_pages = vision_review_max_pages
        self.client = genai.Client(api_key=api_key)

    def _get_call_config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

    def transform_vision(self, page_pngs: List[bytes], doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        parts = [types.Part.from_bytes(data=p, mime_type="image/png") for p in page_pngs]
        initial_prompt = self.vision_prompt
        call_config = self._get_call_config()

        if enable_review:
            if len(page_pngs) <= self.vision_review_max_pages:
                # 頁數在安全門檻內：使用多輪 Chat 進行對照原圖的深度視覺自我審查
                chat = self.client.chats.create(model=self.model_name, config=call_config)
                res1 = retry_call(
                    lambda: chat.send_message(message=[*parts, initial_prompt]),
                    op_name=f"gemini_vision_chat_turn1 ({doc.filename})",
                )

                # 檢查第 1 輪是否遭 Google 安全或版權過濾攔截 (例如 FinishReason.RECITATION)
                cand1 = res1.candidates[0] if (res1 and res1.candidates) else None
                finish_reason1 = getattr(cand1, "finish_reason", None)
                res1_text = clean_markdown_response(res1.text) if res1 and res1.text else ""

                if not res1_text or "RECITATION" in str(finish_reason1):
                    raise RuntimeError(f"Gemini 視覺辨識遭安全過濾阻斷 (finish_reason={finish_reason1})")

                res2 = retry_call(
                    lambda: chat.send_message(message=self.review_prompt),
                    op_name=f"gemini_vision_chat_turn2_review ({doc.filename})",
                )
                md_text = clean_markdown_response(res2.text) if res2 and res2.text else ""
            else:
                # 自適應 Token 節流保護：長篇文件第 1 輪以視覺多模態生成 Markdown 初稿；
                # 第 2 輪切換為文字級結構自我校驗 (避免在 Context 重複發送所有高解析 PNG 圖片)
                response1 = retry_call(
                    lambda: self.client.models.generate_content(
                        model=self.model_name,
                        contents=[*parts, initial_prompt],
                        config=call_config
                    ),
                    op_name=f"gemini_vision_adaptive_turn1 ({doc.filename})",
                )
                cand1 = response1.candidates[0] if (response1 and response1.candidates) else None
                finish_reason1 = getattr(cand1, "finish_reason", None)
                res1_text = clean_markdown_response(response1.text) if response1 and response1.text else ""

                if not res1_text or "RECITATION" in str(finish_reason1):
                    raise RuntimeError(f"Gemini 視覺辨識遭安全過濾阻斷 (finish_reason={finish_reason1})")

                review_text_prompt = f"{self.text_review_prompt}\n\n【初稿內容如下】：\n{res1_text}"
                response2 = retry_call(
                    lambda: self.client.models.generate_content(
                        model=self.model_name,
                        contents=review_text_prompt,
                        config=call_config
                    ),
                    op_name=f"gemini_vision_adaptive_turn2_review ({doc.filename})",
                )
                md_text = clean_markdown_response(response2.text) if response2 and response2.text else res1_text
        else:
            response = retry_call(
                lambda: self.client.models.generate_content(
                    model=self.model_name,
                    contents=[*parts, initial_prompt],
                    config=call_config
                ),
                op_name=f"gemini_vision_oneshot ({doc.filename})",
            )
            cand = response.candidates[0] if (response and response.candidates) else None
            finish_reason = getattr(cand, "finish_reason", None)
            md_text = clean_markdown_response(response.text) if response and response.text else ""
            if not md_text or "RECITATION" in str(finish_reason):
                raise RuntimeError(f"Gemini 視覺辨識遭安全過濾阻斷 (finish_reason={finish_reason})")

        return ConvertedMarkdown(
            content=md_text,
            doc_type=doc.doc_type,
            health=doc.health,
            model_used=self.model_name,
            reviewed=enable_review
        )

    def transform_text(self, text: str, doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        prompt = self.text_prompt_template.format(
            doc_type=doc.doc_type.value.upper(),
            text=text
        )
        call_config = self._get_call_config()

        if enable_review:
            chat = self.client.chats.create(model=self.model_name, config=call_config)
            res1 = retry_call(
                lambda: chat.send_message(message=prompt),
                op_name=f"gemini_text_chat_turn1 ({doc.filename})",
            )
            res2 = retry_call(
                lambda: chat.send_message(message=self.text_review_prompt),
                op_name=f"gemini_text_chat_turn2_review ({doc.filename})",
            )
            md_text = clean_markdown_response(res2.text)
        else:
            response = retry_call(
                lambda: self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=call_config
                ),
                op_name=f"gemini_text_oneshot ({doc.filename})",
            )
            md_text = clean_markdown_response(response.text)

        return ConvertedMarkdown(
            content=md_text,
            doc_type=doc.doc_type,
            health=DocumentHealth.HEALTHY,
            model_used=self.model_name,
            reviewed=enable_review
        )
