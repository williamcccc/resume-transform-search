import functools
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 專案一級資產目錄唯一權威來源 (Single Source of Truth: prompts/)
ROOT_DIR = Path(__file__).resolve().parents[3]
PROMPTS_DIR = ROOT_DIR / "prompts"


@functools.lru_cache(maxsize=16)
def load_prompt(filename: str, fallback_text: Optional[str] = None) -> str:
    """
    從專案根目錄 prompts/ 載入指定的提示詞 Markdown 檔案
    具備 LRU 快取與 fallback 容錯保護
    """
    file_path = PROMPTS_DIR / filename
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8").strip()
        except OSError as err:
            logger.warning(f"讀取提示詞檔案失敗 ({file_path}): {err}")

    if fallback_text is not None:
        return fallback_text.strip()

    raise FileNotFoundError(f"找不到指定的提示詞檔案: {file_path}")
