import json
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.application.dashboard_use_case import GetDashboardDataUseCase
from src.infrastructure.readers.csv_audit_reader import CsvAuditLogReader
from src.infrastructure.readers.file_log_reader import FileAppLogReader
from src.interfaces.web.server import DashboardServer


class TestWebDashboardE2E(unittest.TestCase):
    """Web 儀表板端到端 (E2E) 黑箱/灰箱整合實測"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.td_path = Path(self.temp_dir.name)

        # 建立測試用 CSV
        self.csv_file = self.td_path / "audit_report.csv"
        with open(self.csv_file, "w", encoding="utf-8-sig") as f:
            f.write("Timestamp,Filename,Status,Score,JudgeScore,Model,Reviewed,Warnings\n")
            f.write("2026-11-05 14:00:00,resume1.pdf,SUCCESS,95,90,gemini-3.8-flash,True,None\n")
            f.write("2026-11-05 14:05:00,resume2.pdf,QUARANTINE,55,N/A,gemini-3.8-flash,False,排版鬆散\n")
            f.write("2026-11-05 14:10:00,corrupted.pdf,ERROR,0,N/A,gemini-3.8-flash,False,檔案損毀\n")

        # 建立測試用 log
        self.log_file = self.td_path / "app.log"
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("[2026-11-05 14:00:00] [INFO] [runner:50] - 轉檔任務開始\n")
            f.write("[2026-11-05 14:05:00] [WARNING] [validator:30] - 品質低於門檻: 55\n")
            f.write("[2026-11-05 14:10:00] [ERROR] [runner:99] - 檔案解析異常: corrupted.pdf\n")

        use_case = GetDashboardDataUseCase(
            audit_reader=CsvAuditLogReader(),
            system_log_reader=FileAppLogReader(),
            csv_path=self.csv_file,
            log_path=self.log_file,
        )

        # 綁定 port 0 由 OS 指派閒置埠號
        self.server = DashboardServer(use_case=use_case, host="127.0.0.1", port=0)
        self.server.start(blocking=False)
        self.base_url = f"http://127.0.0.1:{self.server.port}"
        time.sleep(0.1)  # 確保 thread 啟動

    def tearDown(self):
        self.server.stop()
        self.temp_dir.cleanup()

    def test_e2e_serve_dashboard_html(self):
        """E2E-01: 驗證 GET / 回傳 200 OK 且包含完整 HTML 與核心標題"""
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            content_type = resp.headers.get("Content-Type", "")
            self.assertIn("text/html", content_type)
            html_text = resp.read().decode("utf-8")
            self.assertIn("文件轉檔與品管日誌儀表板", html_text)
            self.assertIn("kpiTotal", html_text)

    def test_e2e_api_stats(self):
        """E2E-02: 驗證 GET /api/stats 回傳結構化統計指標 JSON"""
        req = urllib.request.Request(f"{self.base_url}/api/stats")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total_files"], 3)
            self.assertEqual(data["success_count"], 1)
            self.assertEqual(data["quarantined_count"], 1)
            self.assertEqual(data["error_count"], 1)
            self.assertAlmostEqual(data["success_rate"], 33.33, places=1)
            self.assertAlmostEqual(data["avg_score"], 50.0, places=1)
            self.assertAlmostEqual(data["avg_judge_score"], 90.0, places=1)

    def test_e2e_api_audit_with_filters(self):
        """E2E-03: 驗證 GET /api/audit 支援 query 篩選狀態與關鍵字"""
        # 1. 取得全部
        req = urllib.request.Request(f"{self.base_url}/api/audit")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 3)
            self.assertEqual(len(data["items"]), 3)

        # 2. 狀態篩選 QUARANTINE
        req = urllib.request.Request(f"{self.base_url}/api/audit?status=QUARANTINE")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["items"][0]["filename"], "resume2.pdf")

        # 3. 搜尋篩選 "corrupted"
        req = urllib.request.Request(f"{self.base_url}/api/audit?search=corrupted")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["items"][0]["status"], "ERROR")

    def test_e2e_api_logs(self):
        """E2E-04: 驗證 GET /api/logs 回傳日誌與等級過濾"""
        req = urllib.request.Request(f"{self.base_url}/api/logs?level=ERROR")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertIn("檔案解析異常", data["logs"][0]["message"])

    def test_e2e_404_not_found(self):
        """E2E-05: 驗證未知路由回傳 404 JSON 錯誤訊息"""
        req = urllib.request.Request(f"{self.base_url}/api/unknown_endpoint")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 404)

    def test_e2e_fastapi_swagger_and_app(self):
        """E2E-06: 驗證 FastAPI 應用實例能順利提供 Swagger UI /docs 與端點"""
        from fastapi.testclient import TestClient
        from src.interfaces.web.fastapi_server import create_app

        use_case = GetDashboardDataUseCase(
            audit_reader=CsvAuditLogReader(),
            system_log_reader=FileAppLogReader(),
            csv_path=self.csv_file,
            log_path=self.log_file,
        )
        app = create_app(use_case)
        client = TestClient(app)

        # 驗證 Swagger UI 頁面
        res_docs = client.get("/docs")
        self.assertEqual(res_docs.status_code, 200)
        self.assertIn("swagger", res_docs.text.lower())

        # 驗證 ReDoc 頁面
        res_redoc = client.get("/redoc")
        self.assertEqual(res_redoc.status_code, 200)

        # 驗證首頁與 API
        res_home = client.get("/")
        self.assertEqual(res_home.status_code, 200)
        self.assertIn("Swagger API", res_home.text)

        res_stats = client.get("/api/stats")
        self.assertEqual(res_stats.status_code, 200)
        self.assertEqual(res_stats.json()["total_files"], 3)

    def test_e2e_uvicorn_import_from_string_and_factory(self):
        """E2E-07 (TC-18-04): 驗證 Uvicorn 標準目標字串 (fastapi_server:app, create_default_app, web_dashboard:app) 端到端運作"""
        import os
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from uvicorn.importer import import_from_string
        import src.interfaces.web.fastapi_server as fastapi_server_mod

        with patch.dict(
            os.environ,
            {
                "DEFAULT_AUDIT_REPORT": str(self.csv_file),
                "LOG_FILE": str(self.log_file),
            },
        ), patch.object(fastapi_server_mod, "_default_app", None):
            # 1. 驗證 uvicorn src.interfaces.web.fastapi_server:create_default_app --factory
            factory_fn = import_from_string("src.interfaces.web.fastapi_server:create_default_app")
            factory_app = factory_fn()
            factory_client = TestClient(factory_app)
            res_factory_stats = factory_client.get("/api/stats")
            self.assertEqual(res_factory_stats.status_code, 200)
            self.assertEqual(res_factory_stats.json()["total_files"], 3)

            # 2. 驗證 uvicorn src.interfaces.web.fastapi_server:app
            asgi_app = import_from_string("src.interfaces.web.fastapi_server:app")
            asgi_client = TestClient(asgi_app)
            self.assertEqual(asgi_client.get("/").status_code, 200)
            self.assertEqual(asgi_client.get("/docs").status_code, 200)
            self.assertEqual(asgi_client.get("/api/audit").json()["total"], 3)
            self.assertEqual(asgi_client.get("/api/logs").json()["total"], 3)

            # 3. 驗證 uvicorn web_dashboard:app
            root_asgi_app = import_from_string("web_dashboard:app")
            root_client = TestClient(root_asgi_app)
            self.assertEqual(root_client.get("/api/stats").json()["total_files"], 3)


if __name__ == "__main__":
    unittest.main()
