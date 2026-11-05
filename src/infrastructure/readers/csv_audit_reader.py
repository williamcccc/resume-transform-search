import csv
import logging
from pathlib import Path
from typing import List
from src.domain.interfaces import IAuditLogReader
from src.domain.models import AuditRecord

logger = logging.getLogger(__name__)


class CsvAuditLogReader(IAuditLogReader):
    """
    CSV 品管稽核日誌讀取器實作
    安全解析 audit_report.csv，支援 UTF-8-sig 編碼與例外容錯
    """

    def read_audit_records(self, csv_path: Path) -> List[AuditRecord]:
        if not csv_path.exists():
            return []

        records: List[AuditRecord] = []
        try:
            with open(csv_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return []

                # 判定是否有標準欄位
                for row_idx, row in enumerate(reader, start=2):
                    if not row or len(row) < 3:
                        continue
                    try:
                        timestamp = row[0].strip() if len(row) > 0 else ""
                        filename = row[1].strip() if len(row) > 1 else ""
                        status = row[2].strip() if len(row) > 2 else "UNKNOWN"
                        
                        # 解析品質分數
                        score_raw = row[3].strip() if len(row) > 3 else "0"
                        try:
                            score = int(score_raw)
                        except ValueError:
                            score = 0

                        judge_score = row[4].strip() if len(row) > 4 else "N/A"
                        model = row[5].strip() if len(row) > 5 else "unknown"
                        
                        reviewed_raw = row[6].strip().lower() if len(row) > 6 else "false"
                        reviewed = reviewed_raw in ("true", "1", "yes")

                        warnings = row[7].strip() if len(row) > 7 else ""

                        records.append(
                            AuditRecord(
                                timestamp=timestamp,
                                filename=filename,
                                status=status,
                                score=score,
                                judge_score=judge_score,
                                model=model,
                                reviewed=reviewed,
                                warnings=warnings,
                            )
                        )
                    except Exception as parse_err:
                        logger.warning(f"解析 CSV 第 {row_idx} 行異常: {parse_err}")
                        continue
        except Exception as file_err:
            logger.error(f"讀取 CSV 稽核報告失敗 [{csv_path}]: {file_err}")
            return []

        # 預設按時間反向排序（最新排在最前面）
        records.reverse()
        return records
