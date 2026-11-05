import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.application.dashboard_use_case import GetDashboardDataUseCase
from src.application.dto import DashboardQueryDTO
from src.domain.models import AuditRecord, SystemLogRecord
from src.infrastructure.config import AppConfig
from src.infrastructure.readers.csv_audit_reader import CsvAuditLogReader
from src.infrastructure.readers.file_log_reader import FileAppLogReader


class TestWebDashboardUnit(unittest.TestCase):
    """Web 儀表板與日誌查詢單元測試 (100% 離線 Mock 隔離)"""

    def setUp(self):
        self.mock_audit_reader = MagicMock()
        self.mock_log_reader = MagicMock()
        self.use_case = GetDashboardDataUseCase(
            audit_reader=self.mock_audit_reader,
            system_log_reader=self.mock_log_reader,
            csv_path=Path("dummy_audit.csv"),
            log_path=Path("dummy_app.log"),
        )

    def test_empty_audit_and_logs(self):
        """TC-WD-01: 驗證檔案為空或不存在時，統計指標與結果清單優雅回傳預設值而不崩潰"""
        self.mock_audit_reader.read_audit_records.return_value = []
        self.mock_log_reader.read_recent_logs.return_value = []

        result = self.use_case.execute(DashboardQueryDTO())

        self.assertEqual(result.summary.total_files, 0)
        self.assertEqual(result.summary.success_count, 0)
        self.assertEqual(result.summary.quarantined_count, 0)
        self.assertEqual(result.summary.error_count, 0)
        self.assertEqual(result.summary.success_rate, 0.0)
        self.assertEqual(result.summary.avg_score, 0.0)
        self.assertEqual(result.summary.avg_judge_score, 0.0)
        self.assertEqual(len(result.audit_records), 0)
        self.assertEqual(len(result.recent_logs), 0)

    def test_metrics_calculation_and_aggregation(self):
        """TC-WD-02: 驗證多筆稽核資料時，正確計算成功率、平均分與模型分佈"""
        mock_records = [
            AuditRecord(
                timestamp="2026-11-05 10:00:00",
                filename="cand1.pdf",
                status="SUCCESS",
                score=90,
                judge_score="85",
                model="gemini-3.8-flash",
                reviewed=True,
                warnings=""
            ),
            AuditRecord(
                timestamp="2026-11-05 10:01:00",
                filename="cand2.pdf",
                status="QUARANTINE",
                score=50,
                judge_score="N/A",
                model="gemini-3.8-flash",
                reviewed=False,
                warnings="字數過短"
            ),
            AuditRecord(
                timestamp="2026-11-05 10:02:00",
                filename="cand3.pdf",
                status="ERROR",
                score=0,
                judge_score="N/A",
                model="fast_text",
                reviewed=False,
                warnings="檔案損毀"
            ),
            AuditRecord(
                timestamp="2026-11-05 10:03:00",
                filename="cand4.pdf",
                status="SUCCESS",
                score=80,
                judge_score="75",
                model="fast_text",
                reviewed=True,
                warnings=""
            ),
        ]
        self.mock_audit_reader.read_audit_records.return_value = mock_records
        self.mock_log_reader.read_recent_logs.return_value = []

        result = self.use_case.execute(DashboardQueryDTO())
        s = result.summary

        self.assertEqual(s.total_files, 4)
        self.assertEqual(s.success_count, 2)
        self.assertEqual(s.quarantined_count, 1)
        self.assertEqual(s.error_count, 1)
        self.assertEqual(s.success_rate, 50.0)
        # avg_score = (90 + 50 + 0 + 80) / 4 = 55.0
        self.assertEqual(s.avg_score, 55.0)
        # avg_judge_score = (85 + 75) / 2 = 80.0
        self.assertEqual(s.avg_judge_score, 80.0)
        self.assertEqual(s.model_distribution["gemini-3.8-flash"], 2)
        self.assertEqual(s.model_distribution["fast_text"], 2)

    def test_status_and_keyword_filtering(self):
        """TC-WD-03: 驗證狀態篩選與關鍵字搜尋邏輯"""
        mock_records = [
            AuditRecord("2026-11-05", "alice_resume.pdf", "SUCCESS", 95, "N/A", "model1", True, ""),
            AuditRecord("2026-11-05", "bob_cv.pdf", "QUARANTINE", 60, "N/A", "model1", False, "格式損毀"),
            AuditRecord("2026-11-05", "charlie_resume.pdf", "ERROR", 0, "N/A", "model2", False, "超額配額"),
        ]
        self.mock_audit_reader.read_audit_records.return_value = mock_records
        self.mock_log_reader.read_recent_logs.return_value = []

        # 篩選 QUARANTINE
        q1 = DashboardQueryDTO(status="QUARANTINE")
        res1 = self.use_case.execute(q1)
        self.assertEqual(len(res1.audit_records), 1)
        self.assertEqual(res1.audit_records[0].filename, "bob_cv.pdf")

        # 關鍵字篩選 "resume"
        q2 = DashboardQueryDTO(search="resume")
        res2 = self.use_case.execute(q2)
        self.assertEqual(len(res2.audit_records), 2)

    def test_pagination(self):
        """TC-WD-04: 驗證稽核分頁 offset 與 limit 截斷正確"""
        mock_records = [
            AuditRecord("2026-11-05", f"cand_{i}.pdf", "SUCCESS", 90, "N/A", "m", False, "")
            for i in range(10)
        ]
        self.mock_audit_reader.read_audit_records.return_value = mock_records
        self.mock_log_reader.read_recent_logs.return_value = []

        q = DashboardQueryDTO(offset=2, limit=3)
        res = self.use_case.execute(q)
        self.assertEqual(res.total_audit_records, 10)
        self.assertEqual(len(res.audit_records), 3)
        self.assertEqual(res.audit_records[0].filename, "cand_2.pdf")
        self.assertEqual(res.audit_records[2].filename, "cand_4.pdf")

    def test_system_log_filtering(self):
        """TC-WD-05: 驗證系統日誌等級與關鍵字過濾"""
        mock_logs = [
            SystemLogRecord("2026-11-05 12:00:00", "INFO", "main", "系統啟動完成"),
            SystemLogRecord("2026-11-05 12:01:00", "WARNING", "runner", "字數不足警告"),
            SystemLogRecord("2026-11-05 12:02:00", "ERROR", "gemini", "API 429 配額用罄"),
        ]
        self.mock_audit_reader.read_audit_records.return_value = []
        self.mock_log_reader.read_recent_logs.return_value = mock_logs

        q = DashboardQueryDTO(log_level="ERROR")
        res = self.use_case.execute(q)
        self.assertEqual(len(res.recent_logs), 1)
        self.assertIn("API 429", res.recent_logs[0].message)

    def test_csv_audit_reader_real_file(self):
        """TC-WD-06: 驗證 CsvAuditLogReader 解析實體 CSV 檔案並正確處理欄位"""
        with tempfile.TemporaryDirectory() as td:
            csv_file = Path(td) / "test_audit.csv"
            with open(csv_file, "w", encoding="utf-8-sig") as f:
                f.write("Timestamp,Filename,Status,Score,JudgeScore,Model,Reviewed,Warnings\n")
                f.write("2026-11-05 14:00:00,test1.pdf,SUCCESS,92,88,gemini-3.8-flash,True,None\n")
                f.write("2026-11-05 14:01:00,test2.pdf,QUARANTINE,45,N/A,gemini-3.8-flash,False,缺少H1\n")

            reader = CsvAuditLogReader()
            records = reader.read_audit_records(csv_file)
            self.assertEqual(len(records), 2)
            # 預設 reverse (最新排前面)
            self.assertEqual(records[0].filename, "test2.pdf")
            self.assertEqual(records[0].status, "QUARANTINE")
            self.assertEqual(records[0].score, 45)
            self.assertEqual(records[1].filename, "test1.pdf")
            self.assertTrue(records[1].reviewed)

    def test_file_log_reader_real_file(self):
        """TC-WD-07: 驗證 FileAppLogReader 正則提取實體 log 檔案"""
        with tempfile.TemporaryDirectory() as td:
            log_file = Path(td) / "test.log"
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("[2026-11-05 14:10:00] [INFO] [server:42] - 服務啟動於 8080\n")
                f.write("[2026-11-05 14:11:00] [ERROR] [runner:99] - 檔案解析例外\n")

            reader = FileAppLogReader()
            records = reader.read_recent_logs(log_file)
            self.assertEqual(len(records), 2)
            # 預設 reverse
            self.assertEqual(records[0].level, "ERROR")
            self.assertEqual(records[0].logger, "runner:99")
            self.assertEqual(records[1].level, "INFO")

    def test_app_config_web_settings(self):
        """TC-WD-08: 驗證 AppConfig 支援 Web 參數覆寫與預設值"""
        cfg = AppConfig.load(
            override_api_key="mock",
            override_web_host="0.0.0.0",
            override_web_port=9090,
            override_web_engine="fastapi",
        )
        self.assertEqual(cfg.web_host, "0.0.0.0")
        self.assertEqual(cfg.web_port, 9090)
        self.assertEqual(cfg.web_engine, "fastapi")

    def test_fastapi_app_endpoints(self):
        """TC-WD-09: 驗證 FastAPI 實例路由、OpenAPI 文件與端點回應"""
        from fastapi.testclient import TestClient
        from src.interfaces.web.fastapi_server import create_app

        mock_records = [
            AuditRecord("2026-11-05", "test.pdf", "SUCCESS", 90, "85", "gemini-3.8-flash", True, "")
        ]
        self.mock_audit_reader.read_audit_records.return_value = mock_records
        self.mock_log_reader.read_recent_logs.return_value = []

        app = create_app(self.use_case)
        client = TestClient(app)

        # 1. 測試 OpenAPI /docs /openapi.json
        res_open = client.get("/openapi.json")
        self.assertEqual(res_open.status_code, 200)
        self.assertIn("文件轉檔與品管日誌儀表板 API", res_open.text)

        # 2. 測試 GET /
        res_home = client.get("/")
        self.assertEqual(res_home.status_code, 200)
        self.assertIn("text/html", res_home.headers.get("content-type", ""))

        # 3. 測試 GET /api/stats
        res_stats = client.get("/api/stats")
        self.assertEqual(res_stats.status_code, 200)
        data = res_stats.json()
        self.assertEqual(data["total_files"], 1)
        self.assertEqual(data["success_count"], 1)

        # 4. 測試 GET /api/audit
        res_audit = client.get("/api/audit?status=SUCCESS")
        self.assertEqual(res_audit.status_code, 200)
        audit_data = res_audit.json()
        self.assertEqual(audit_data["total"], 1)
        self.assertEqual(audit_data["items"][0]["filename"], "test.pdf")

    def test_build_web_use_cases_normal_and_fault_degradation(self):
        """TC-18-01: 驗證 build_web_use_cases 正常組裝與檢索服務故障注入時之優雅降級"""
        from unittest.mock import patch
        from src.interfaces.web.server import build_web_use_cases

        # 1. Arrange
        cfg = AppConfig.load(
            override_api_key="mock_key",
            override_audit_report="dummy_audit.csv",
            override_log_file="dummy_app.log",
        )

        # 2. Act (Happy Path)
        uc, search_uc, init_err = build_web_use_cases(cfg)

        # 3. Assert (Happy Path)
        self.assertIsInstance(uc, GetDashboardDataUseCase)
        self.assertIsNotNone(search_uc)
        self.assertIsNone(init_err)

        # 4. Act & Assert (Fault Injection: 模擬 RedisVectorStore 初始化拋出異常)
        with patch(
            "src.infrastructure.stores.redis_vector_store.RedisVectorStore",
            side_effect=RuntimeError("模擬向量庫配置異常"),
        ):
            uc_fallback, search_uc_fallback, init_err_fallback = build_web_use_cases(cfg)
            self.assertIsInstance(uc_fallback, GetDashboardDataUseCase)
            self.assertIsNone(search_uc_fallback)
            self.assertIsInstance(init_err_fallback, RuntimeError)
            self.assertIn("模擬向量庫配置異常", str(init_err_fallback))

    def test_create_default_app_factory_with_custom_config(self):
        """TC-18-02: 驗證 create_default_app ASGI Factory 可搭配 AppConfig 直接建立可用之 FastAPI 實例"""
        from fastapi.testclient import TestClient
        from src.interfaces.web.fastapi_server import create_default_app

        # 1. Arrange
        with tempfile.TemporaryDirectory() as td:
            csv_file = Path(td) / "factory_audit.csv"
            log_file = Path(td) / "factory_app.log"
            with open(csv_file, "w", encoding="utf-8-sig") as f:
                f.write("Timestamp,Filename,Status,Score,JudgeScore,Model,Reviewed,Warnings\n")
                f.write("2026-11-05 15:00:00,sample_resume.pdf,SUCCESS,96,92,gemini-3.8-flash,True,None\n")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("[2026-11-05 15:00:00] [INFO] [factory:10] - Factory 測試啟動\n")

            cfg = AppConfig.load(
                override_api_key="mock_key",
                override_audit_report=str(csv_file),
                override_log_file=str(log_file),
            )

            # 2. Act
            app = create_default_app(cfg)
            client = TestClient(app)
            resp = client.get("/api/stats")

            # 3. Assert
            self.assertEqual(resp.status_code, 200)
            stats = resp.json()
            self.assertEqual(stats["total_files"], 1)
            self.assertEqual(stats["success_count"], 1)
            self.assertEqual(stats["avg_score"], 96.0)

    def test_lazy_module_app_attribute_and_invalid_attribute_error(self):
        """TC-18-03: 驗證 fastapi_server:app 與 web_dashboard:app 支援 PEP 562 延遲載入與非法屬性阻斷"""
        from unittest.mock import patch
        from fastapi import FastAPI
        import src.interfaces.web.fastapi_server as fastapi_server_mod
        import web_dashboard as web_dashboard_mod

        # 1. Arrange
        dummy_app = FastAPI(title="Mock Lazy App")

        # 2. Act & Assert: 驗證延遲載入屬性 "app"
        with patch.object(fastapi_server_mod, "_default_app", None), patch.object(
            fastapi_server_mod, "create_default_app", return_value=dummy_app
        ) as mock_factory:
            resolved_app = getattr(fastapi_server_mod, "app")
            self.assertIs(resolved_app, dummy_app)
            mock_factory.assert_called_once()

            resolved_root_app = getattr(web_dashboard_mod, "app")
            self.assertIs(resolved_root_app, dummy_app)

        # 3. Act & Assert (Negative Path): 非法屬性名稱必須拋出 AttributeError
        with self.assertRaises(AttributeError):
            _ = getattr(fastapi_server_mod, "non_existent_uvicorn_attr")

        with self.assertRaises(AttributeError):
            _ = getattr(web_dashboard_mod, "non_existent_uvicorn_attr")


if __name__ == "__main__":
    unittest.main()
