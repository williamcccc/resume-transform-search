import logging
import os
import time
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


def clean_markdown_response(text: str) -> str:
    """清理 LLM 輸出的 Markdown 標記，去除外層的 ```markdown 標籤"""
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[len("```markdown"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def retry_call(
    func: Callable[[], Any],
    max_retries: Optional[int] = None,
    initial_delay: Optional[float] = None,
    op_name: str = "api_call",
) -> Any:
    """暫時性網路或伺服器忙碌重試 (503 / 429 RPM)，支援耗時監控與 .env (API_MAX_RETRIES, API_RETRY_DELAY) 配置"""
    if max_retries is None:
        try:
            max_retries = int(os.environ.get("API_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3

    if initial_delay is None:
        try:
            initial_delay = float(os.environ.get("API_RETRY_DELAY", "2.0"))
        except ValueError:
            initial_delay = 2.0

    start_total = time.perf_counter()

    for attempt in range(max_retries):
        attempt_start = time.perf_counter()
        try:
            result = func()
            elapsed = time.perf_counter() - attempt_start
            total_elapsed = time.perf_counter() - start_total
            logger.info(
                "API 請求成功 [%s] - 當次耗時: %.3f 秒, 累計總耗時: %.3f 秒 (第 %d 次嘗試)",
                op_name,
                elapsed,
                total_elapsed,
                attempt + 1,
            )
            return result
        except Exception as e:
            err_msg = str(e)
            err_lower = err_msg.lower()
            attempt_elapsed = time.perf_counter() - attempt_start

            # 若為每日配額耗盡 (Daily Quota Exceeded)，短暫重試無效，直接向上拋出以便記錄日誌
            if (
                "requests per day" in err_lower
                or "requestsperday" in err_lower
                or "free_tier_requests" in err_lower
                or "limit exceeded on free tier" in err_lower
            ):
                total_elapsed = time.perf_counter() - start_total
                logger.error(
                    "API 請求每日配額用罄 [%s] - 耗時: %.3f 秒 (第 %d 次嘗試): %s",
                    op_name,
                    total_elapsed,
                    attempt + 1,
                    err_msg[:120],
                )
                raise e

            is_transient = any(code in err_msg for code in ["503", "UNAVAILABLE", "ConnectError", "getaddrinfo failed"])
            # 只有短期每分鐘速率限制 (RPM) 才值得短暫重試
            if "429" in err_msg and ("per minute" in err_lower or "rpm" in err_lower):
                is_transient = True

            if attempt < max_retries - 1 and is_transient:
                sleep_sec = initial_delay * (2 ** attempt)
                logger.warning(
                    "API 請求暫時性異常 [%s] - 耗時: %.3f 秒, 原因: %s, 將於 %.2f 秒後進行第 %d/%d 次重試",
                    op_name,
                    attempt_elapsed,
                    err_msg[:120],
                    sleep_sec,
                    attempt + 2,
                    max_retries,
                )
                time.sleep(sleep_sec)
            else:
                total_elapsed = time.perf_counter() - start_total
                logger.error(
                    "API 請求最終失敗 [%s] - 累計總耗時: %.3f 秒, 最終錯誤: %s (嘗試次數: %d)",
                    op_name,
                    total_elapsed,
                    err_msg[:120],
                    attempt + 1,
                )
                raise e
