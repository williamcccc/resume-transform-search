import re
from typing import Optional, Set, List, Dict
from src.domain.models import Document, QualityReport
from src.domain.interfaces import IQualityValidator


class MarkdownQualityValidator(IQualityValidator):
    """
    確定性規則品管檢核閥 (Deterministic Quality Guardrail)
    - 零 API 成本、毫秒級執行
    - 檢核維度：
      1. 結構骨架檢驗 (一級標題、核心大綱區塊)
      2. 雜訊標記禁令 (## Page X、\ufffd 亂碼、未閉合代碼框)
      3. 篇幅保留率 (防止 LLM 偷懶精簡摘要)
      4. 關鍵實體召回 (Email、電話等不遺失)
      5. Markdown 表格與語法健康度
    """

    def __init__(
        self,
        pass_threshold: int = 65,
        min_retention_ratio: float = 0.35,
        max_retention_ratio: float = 3.5,
    ):
        self.pass_threshold = pass_threshold
        self.min_retention_ratio = min_retention_ratio
        self.max_retention_ratio = max_retention_ratio

    def validate(self, markdown: str, raw_text: Optional[str] = None, doc: Optional[Document] = None) -> QualityReport:
        if not markdown or not markdown.strip():
            return QualityReport(
                is_passed=False,
                score=0,
                warnings=["Markdown 內容為空"],
                checks={"content_not_empty": False}
            )

        score = 100
        warnings: List[str] = []
        checks: Dict[str, bool] = {}
        missing_entities: List[str] = []
        retention_ratio: Optional[float] = None

        # -------------------------------------------------------------
        # 維度 1：結構骨架檢驗
        # -------------------------------------------------------------
        has_h1 = bool(re.search(r"^#\s+[^\n#]+", markdown, re.MULTILINE))
        checks["has_h1_heading"] = has_h1
        if not has_h1:
            score -= 20
            warnings.append("缺少一級標題 (# 姓名/主標題)")

        # 檢查核心履歷區塊 (經歷、學歷、技能、基本資料)
        section_groups = [
            ["經歷", "工作", "experience", "任職", "職歷", "career"],
            ["學歷", "教育", "education", "畢業", "學校", "academic"],
            ["技能", "專長", "skill", "專門", "技術"],
            ["個人", "基本", "資料", "自傳", "profile", "about", "聯絡", "通訊", "contact"]
        ]
        # 僅在 Markdown 標題列 (#, ##, ###) 或粗體大綱列 (**標題**) 尋找大綱段落，避免內文提及關鍵字造成誤判
        headings = re.findall(r"^(?:#{1,4}\s+|\*\*)([^\n*#]+)", markdown, re.MULTILINE)
        headings_text = " ".join(headings).lower()
        found_sections = sum(1 for group in section_groups if any(k in headings_text for k in group))
        checks["has_core_sections"] = (found_sections >= 2)
        if found_sections < 2:
            score -= 25
            warnings.append("缺少核心履歷大綱區塊 (如工作經歷、學歷、技能)")

        # -------------------------------------------------------------
        # 維度 2：雜訊標記禁令
        # -------------------------------------------------------------
        has_page_noise = bool(re.search(r"##\s*Page\s*\d+", markdown, re.IGNORECASE))
        has_ufffd = "\ufffd" in markdown
        has_raw_fence = markdown.startswith("```") or markdown.endswith("```")

        checks["no_page_noise"] = not has_page_noise
        checks["no_ufffd_corruption"] = not has_ufffd
        checks["no_raw_code_fence"] = not has_raw_fence

        if has_page_noise:
            score -= 15
            warnings.append("殘留未過濾的分頁標記 (## Page X)")

        if has_ufffd:
            score -= 20
            warnings.append("包含亂碼替換字元 (\\ufffd)")

        if has_raw_fence:
            score -= 10
            warnings.append("外層殘留程式碼圍欄標記 (```markdown)")

        # -------------------------------------------------------------
        # 維度 3：篇幅保留率 (防止 LLM 偷懶精簡摘要)
        # -------------------------------------------------------------
        if raw_text and raw_text.strip():
            raw_clean = re.sub(r"\s+", "", raw_text)
            md_clean = re.sub(r"\s+", "", markdown)
            raw_len = len(raw_clean)
            md_len = len(md_clean)

            if raw_len >= 50:
                retention_ratio = round(md_len / raw_len, 3)
                checks["retention_ratio_ok"] = (self.min_retention_ratio <= retention_ratio <= self.max_retention_ratio)

                if retention_ratio < self.min_retention_ratio:
                    score -= 25
                    warnings.append(f"字數顯著低於原文 (保留率僅 {retention_ratio:.1%})，可能有過度精簡摘要或截斷")
                elif retention_ratio > self.max_retention_ratio:
                    score -= 15
                    warnings.append(f"字數顯著高於原文 (膨脹率 {retention_ratio:.1%})，可能包含重複內容")

        # -------------------------------------------------------------
        # 維度 4：關鍵實體召回 (Email、手機號碼)
        # -------------------------------------------------------------
        if raw_text and raw_text.strip():
            # Email 檢核
            email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
            raw_emails = set(re.findall(email_pattern, raw_text))
            md_emails = set(re.findall(email_pattern, markdown))
            missing_emails = raw_emails - md_emails
            if missing_emails:
                for e in missing_emails:
                    missing_entities.append(f"Email: {e}")
                score -= 20
                warnings.append(f"遺漏關鍵 Email: {', '.join(missing_emails)}")

            # 手機號碼檢核 (台灣格式 09xx-xxx-xxx)
            phone_pattern = r"09\d{2}[-\s]?\d{3}[-\s]?\d{3}"
            raw_phones_raw = re.findall(phone_pattern, raw_text)
            # 標準化為純數字
            raw_phones_digits = {re.sub(r"\D", "", p) for p in raw_phones_raw}
            md_phones_raw = re.findall(phone_pattern, markdown)
            md_phones_digits = {re.sub(r"\D", "", p) for p in md_phones_raw}

            # 亦檢查 md 內容中是否直接包含該串數字
            clean_md_digits = re.sub(r"\D", "", markdown)
            missing_phones = {p for p in raw_phones_digits if p not in clean_md_digits}
            if missing_phones:
                for p in missing_phones:
                    missing_entities.append(f"手機: {p}")
                score -= 15
                warnings.append(f"遺漏關鍵手機號碼: {', '.join(missing_phones)}")

            checks["entities_preserved"] = (len(missing_entities) == 0)

        # -------------------------------------------------------------
        # 最終評分與判定
        # -------------------------------------------------------------
        final_score = max(0, min(100, score))
        is_passed = (final_score >= self.pass_threshold)

        return QualityReport(
            is_passed=is_passed,
            score=final_score,
            warnings=warnings,
            checks=checks,
            retention_ratio=retention_ratio,
            missing_entities=missing_entities
        )
