import re
from pathlib import Path
from typing import Optional, List, Dict
from src.domain.interfaces import IAuditLogReader, ISystemLogReader
from src.domain.models import AuditRecord, DashboardSummary, SystemLogRecord
from src.application.dto import DashboardQueryDTO, DashboardResultDTO


class GetDashboardDataUseCase:
    """
    轉檔日誌與統計摘要查詢使用案例 (Use Case)
    純粹依賴 Domain Protocol，協調 Audit 與 System Log Readers，進行業務聚合與篩選
    """

    def __init__(
        self,
        audit_reader: IAuditLogReader,
        system_log_reader: ISystemLogReader,
        csv_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
    ):
        self._audit_reader = audit_reader
        self._system_log_reader = system_log_reader
        self._csv_path = csv_path or Path("logs/audit_report.csv")
        self._log_path = log_path or Path("logs/app.log")

    def execute(self, query: Optional[DashboardQueryDTO] = None) -> DashboardResultDTO:
        if query is None:
            query = DashboardQueryDTO()

        # 1. 讀取所有品管稽核紀錄
        all_audit_records = self._audit_reader.read_audit_records(self._csv_path)

        # 2. 統計匯總 (Summary Metrics)
        total_files = len(all_audit_records)
        success_count = sum(1 for r in all_audit_records if r.status.upper() == "SUCCESS")
        quarantined_count = sum(1 for r in all_audit_records if r.status.upper() == "QUARANTINE")
        error_count = sum(1 for r in all_audit_records if r.status.upper() == "ERROR")

        success_rate = round((success_count / total_files * 100), 2) if total_files > 0 else 0.0
        avg_score = round(sum(r.score for r in all_audit_records) / total_files, 1) if total_files > 0 else 0.0

        judge_scores: List[float] = []
        for r in all_audit_records:
            if r.judge_score and r.judge_score.strip().upper() != "N/A":
                try:
                    judge_scores.append(float(r.judge_score))
                except ValueError:
                    pass
        avg_judge_score = round(sum(judge_scores) / len(judge_scores), 1) if judge_scores else 0.0

        model_distribution: Dict[str, int] = {}
        for r in all_audit_records:
            model_key = r.model if r.model else "unknown"
            model_distribution[model_key] = model_distribution.get(model_key, 0) + 1

        summary = DashboardSummary(
            total_files=total_files,
            success_count=success_count,
            quarantined_count=quarantined_count,
            error_count=error_count,
            success_rate=success_rate,
            avg_score=avg_score,
            avg_judge_score=avg_judge_score,
            model_distribution=model_distribution,
        )

        # 3. 稽核紀錄篩選與分頁
        filtered_audit = all_audit_records
        if query.status and query.status.strip().upper() != "ALL":
            status_target = query.status.strip().upper()
            filtered_audit = [r for r in filtered_audit if r.status.upper() == status_target]

        if query.search and query.search.strip():
            kw = query.search.strip().lower()
            filtered_audit = [
                r for r in filtered_audit
                if kw in r.filename.lower() or kw in r.warnings.lower() or kw in r.model.lower()
            ]

        total_audit_records = len(filtered_audit)
        paged_audit = filtered_audit[query.offset : query.offset + query.limit]

        # 4. 系統日誌讀取與篩選
        raw_logs = self._system_log_reader.read_recent_logs(self._log_path, max_lines=max(query.max_log_lines * 5, 500))
        filtered_logs = raw_logs

        if query.log_level and query.log_level.strip().upper() != "ALL":
            level_target = query.log_level.strip().upper()
            filtered_logs = [l for l in filtered_logs if l.level.upper() == level_target]

        if query.log_search and query.log_search.strip():
            log_kw = query.log_search.strip().lower()
            filtered_logs = [
                l for l in filtered_logs
                if log_kw in l.message.lower() or log_kw in l.logger.lower()
            ]

        total_log_records = len(filtered_logs)
        sliced_logs = filtered_logs[: query.max_log_lines]

        return DashboardResultDTO(
            summary=summary,
            audit_records=paged_audit,
            total_audit_records=total_audit_records,
            recent_logs=sliced_logs,
            total_log_records=total_log_records,
        )
