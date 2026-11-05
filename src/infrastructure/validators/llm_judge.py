import json
import re
from typing import List, Optional
from google import genai
from google.genai import types

from src.domain.interfaces import ILlmJudge
from src.domain.models import Document, JudgeScorecard
from src.infrastructure.prompts import load_prompt
from src.infrastructure.transformers.utils import retry_call

# 從獨立檔案載入 Prompt Engineering 提示詞 (便於 Git 版控與獨立優化)
JUDGE_SYSTEM_PROMPT = load_prompt("judge_system.md")
JUDGE_VISION_PROMPT_TEMPLATE = load_prompt("judge_vision_prompt.md")
JUDGE_TEXT_PROMPT_TEMPLATE = load_prompt("judge_text_prompt.md")


class GeminiLlmJudge(ILlmJudge):
    """
    Google Gemini 獨立客觀評審員實作 (LLM-as-a-Judge)
    - 支援對照 PDF 原始渲染頁面影像或 Word 原始文字進行評審
    - 輸出結構化 JSON 評分卡
    """
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.8-flash",
        system_prompt: Optional[str] = None,
        vision_prompt_template: Optional[str] = None,
        text_prompt_template: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.system_prompt = system_prompt or JUDGE_SYSTEM_PROMPT
        self.vision_prompt_template = vision_prompt_template or JUDGE_VISION_PROMPT_TEMPLATE
        self.text_prompt_template = text_prompt_template or JUDGE_TEXT_PROMPT_TEMPLATE
        self.client = genai.Client(api_key=api_key)

    def judge_document(
        self,
        markdown: str,
        doc: Document,
        page_pngs: Optional[List[bytes]] = None,
        raw_text: Optional[str] = None
    ) -> JudgeScorecard:
        parts = []
        if page_pngs:
            for p in page_pngs:
                parts.append(types.Part.from_bytes(data=p, mime_type="image/png"))
            prompt = self.vision_prompt_template.format(
                system_prompt=self.system_prompt,
                filename=doc.filename,
                doc_type=doc.doc_type.value.upper(),
                markdown=markdown,
            )
            parts.append(prompt)
        else:
            full_prompt = self.text_prompt_template.format(
                system_prompt=self.system_prompt,
                filename=doc.filename,
                doc_type=doc.doc_type.value.upper(),
                markdown=markdown,
                raw_text=raw_text or "（無文字層或已為純掃描檔）",
            )
            parts.append(full_prompt)


        call_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

        mode_str = "vision" if page_pngs else "text"
        response = retry_call(
            lambda: self.client.models.generate_content(
                model=self.model_name,
                contents=parts,
                config=call_config
            ),
            op_name=f"gemini_judge_eval_{mode_str} ({doc.filename})",
        )

        return self._parse_json_scorecard(response.text)

    def _parse_json_scorecard(self, text: str) -> JudgeScorecard:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        try:
            data = json.loads(cleaned)
            overall = int(data.get("overall_score", 70))
            comp = int(data.get("completeness_score", overall))
            fid = int(data.get("fidelity_score", overall))
            stru = int(data.get("structure_score", overall))
            verdict = str(data.get("verdict", "PASS" if overall >= 80 else ("WARNING" if overall >= 60 else "FAIL"))).upper()
            critique = str(data.get("critique", "LLM 評審完成。"))
            missing = list(data.get("missing_items", []))
            hallu = list(data.get("hallucinations", []))

            return JudgeScorecard(
                overall_score=overall,
                completeness_score=comp,
                fidelity_score=fid,
                structure_score=stru,
                verdict=verdict,
                critique=critique,
                missing_items=missing,
                hallucinations=hallu,
                raw_json=cleaned
            )
        except Exception:
            return JudgeScorecard(
                overall_score=70,
                completeness_score=70,
                fidelity_score=70,
                structure_score=70,
                verdict="WARNING",
                critique=f"無法完全解析評判員 JSON 回應，原始內容摘要: {cleaned[:100]}",
                raw_json=cleaned
            )
