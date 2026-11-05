import re
from typing import Tuple, Optional


def parse_experience_years(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    從履歷 Markdown 全文或切片內容中，智能萃取工作年資數值與原始敘述
    回傳: (years_float, raw_expression_str)
    例如: (4.0, "4~5年工作經歷")
    """
    if not text:
        return None, None

    # 1. 優先匹配履歷頭部或基本資料中的工作年資欄位
    # 例: - **工作經歷**：4~5年工作經歷
    # 例: - **經歷**：5年以上
    # 例: - **總工作年資**：6年3個月
    header_match = re.search(
        r"(?:工作經歷|經歷|總年資|工作年資|相關經歷)[^\n]*?[:：]\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    )

    if header_match:
        raw_str = header_match.group(1).strip()
        # 清除 markdown 殘留符號
        clean_str = re.sub(r"[\*`_#]", "", raw_str).strip()

        # A. 區間年資: 4~5年, 1-2年, 3至4年 -> 取保守下限 4.0
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*[~～至\-]\s*(\d+(?:\.\d+)?)\s*年", clean_str)
        if range_match:
            try:
                min_y = float(range_match.group(1))
                return min_y, clean_str
            except ValueError:
                pass

        # B. 門檻型年資: 5年以上, 10年+
        threshold_match = re.search(r"(\d+(?:\.\d+)?)\s*年\s*(?:以上|\+)", clean_str)
        if threshold_match:
            try:
                return float(threshold_match.group(1)), clean_str
            except ValueError:
                pass

        # C. 具體年月: 3年, 3年6個月
        year_month_match = re.search(r"(\d+(?:\.\d+)?)\s*年(?:\s*(\d+)\s*個?月)?", clean_str)
        if year_month_match:
            try:
                years = float(year_month_match.group(1))
                months = float(year_month_match.group(2)) if year_month_match.group(2) else 0.0
                total = round(years + (months / 12.0), 1)
                return total, clean_str
            except ValueError:
                pass

        # D. 純月數: 11個月
        month_match = re.search(r"(\d+)\s*個?月", clean_str)
        if month_match:
            try:
                months = float(month_match.group(1))
                return round(months / 12.0, 1), clean_str
            except ValueError:
                pass

    # 2. 內文直接描述型年資（如：擁有 5 年以上開發經驗、累積 2 年相關實務）
    inline_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:~|～|-|至)?\s*(\d+(?:\.\d+)?)?\s*年\s*(?:以上|\+|工作經歷|工作經驗|相關經歷|實務|開發經驗)",
        text,
        re.IGNORECASE
    )
    if inline_match:
        try:
            val = float(inline_match.group(1))
            return val, inline_match.group(0).strip()
        except ValueError:
            pass

    # 3. 次要方案：掃描各段經歷任職期間（如：2018/06 ～ 2021/08（3年2個月）），進行累積加總
    tenure_matches = re.findall(r"[（\(](\d+)\s*年(?:\s*(\d+)\s*個?月)?[）\)]", text)
    if tenure_matches:
        total_accumulated = 0.0
        for y_str, m_str in tenure_matches:
            y = float(y_str) if y_str else 0.0
            m = float(m_str) if m_str else 0.0
            total_accumulated += y + (m / 12.0)
        if total_accumulated > 0:
            return round(total_accumulated, 1), f"累積各任職約 {round(total_accumulated, 1)} 年"

    return None, None


class RegexExperienceParser:
    """正則工作年資解析器實作 (實作 IExperienceParser 契約)"""
    def parse(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        return parse_experience_years(text)
