import re
import logging
from pathlib import Path
from typing import List
from src.domain.interfaces import ISystemLogReader
from src.domain.models import SystemLogRecord

logger = logging.getLogger(__name__)

# 標準日誌格式正規表達式: [時間戳] [等級] [模組:行號] - 訊息
LOG_PATTERN = re.compile(r"^\[(.*?)\]\s+\[(.*?)\]\s+\[(.*?)\]\s+-\s+(.*)$")


class FileAppLogReader(ISystemLogReader):
    """
    本機檔案系統技術日誌讀取器實作
    安全解析 app.log，支援正則匹配與行數截斷
    """

    def read_recent_logs(self, log_path: Path, max_lines: int = 1000) -> List[SystemLogRecord]:
        if not log_path.exists():
            return []

        records: List[SystemLogRecord] = []
        try:
            with open(log_path, mode="r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # 抓取最後 max_lines 行
            recent_lines = lines[-max_lines:] if len(lines) > max_lines else lines

            for line in recent_lines:
                line_str = line.strip()
                if not line_str:
                    continue
                match = LOG_PATTERN.match(line_str)
                if match:
                    timestamp, level, logger_name, message = match.groups()
                    records.append(
                        SystemLogRecord(
                            timestamp=timestamp.strip(),
                            level=level.strip(),
                            logger=logger_name.strip(),
                            message=message.strip(),
                        )
                    )
                else:
                    # 非標準行（例如多行堆疊 Traceback 的續行）
                    if records:
                        records[-1].message += f"\n{line_str}"
                    else:
                        records.append(
                            SystemLogRecord(
                                timestamp="",
                                level="INFO",
                                logger="raw",
                                message=line_str,
                            )
                        )
        except Exception as read_err:
            logger.error(f"讀取系統日誌失敗 [{log_path}]: {read_err}")
            return []

        # 最新的排在最前面
        records.reverse()
        return records
