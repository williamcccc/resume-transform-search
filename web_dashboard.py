#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_dashboard.py
----------------
轉檔日誌與品管統計摘要 Web 查詢儀表板 CLI 與 ASGI 入口點。
支援雙引擎啟動：
1. 標準 CLI 啟動: python web_dashboard.py [--open] [--port 8080]
2. 標準 Uvicorn 啟動:
   - python -m uvicorn src.interfaces.web.fastapi_server:app --reload
   - python -m uvicorn src.interfaces.web.fastapi_server:create_default_app --factory --reload
   - python -m uvicorn web_dashboard:app --reload
"""

import argparse
import logging
import os
import sys
import webbrowser
from pathlib import Path

# 確保 Windows 終端輸出 UTF-8 編碼，避免 CP950 亂碼
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 將專案根目錄加入模組搜尋路徑
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.infrastructure.config import AppConfig
from src.interfaces.web.server import DashboardServer, build_web_use_cases

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("web_dashboard")


def parse_args():
    parser = argparse.ArgumentParser(
        description="⚡ 履歷轉檔與品管日誌 Web 查詢儀表板 (Conversion Dashboard)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
啟動方式範例:
  # 1. 標準 CLI 啟動 (自動偵測 FastAPI 或內建伺服器，並開啟瀏覽器)
  python web_dashboard.py --open --port 8080

  # 2. 標準 Uvicorn 頂層 app 啟動 (支援 --reload 開發熱重載)
  python -m uvicorn src.interfaces.web.fastapi_server:app --reload --port 8080
  python -m uvicorn web_dashboard:app --reload --port 8080

  # 3. 標準 Uvicorn ASGI Factory 啟動
  python -m uvicorn src.interfaces.web.fastapi_server:create_default_app --factory --reload --port 8080
""",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Web 伺服器監聽 IP (預設讀取 WEB_HOST 或 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Web 伺服器監聽埠號 (預設讀取 WEB_PORT 或 8080)"
    )
    parser.add_argument(
        "--audit-file",
        type=str,
        default=None,
        help="轉檔品管 CSV 報告檔案路徑 (預設 logs/audit_report.csv)"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="系統技術日誌檔案路徑 (預設 logs/app.log)"
    )
    parser.add_argument(
        "--engine",
        type=str,
        choices=["auto", "fastapi", "builtin"],
        default=None,
        help="Web 伺服器引擎 (auto: 優先 FastAPI，未安裝自動降級; fastapi: 強制 FastAPI; builtin: 內建標準庫)"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="啟動後自動於預設瀏覽器中開啟儀表板網頁"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = AppConfig.load(
        override_web_host=args.host,
        override_web_port=args.port,
        override_web_engine=args.engine,
        override_audit_report=args.audit_file,
        override_log_file=args.log_file,
    )

    host = config.web_host
    port = config.web_port
    engine = config.web_engine
    audit_path = Path(config.default_audit_report or "logs/audit_report.csv")
    log_path = Path(config.log_file or "logs/app.log")

    # 組裝依賴 (Dependency Injection Bootstrap)
    use_case, search_use_case, search_init_err = build_web_use_cases(config)

    url = f"http://{host}:{port}"
    docs_url = f"http://{host}:{port}/docs"
    redoc_url = f"http://{host}:{port}/redoc"

    # 決定伺服器啟動模式
    use_fastapi = False
    if engine in ("auto", "fastapi"):
        try:
            import fastapi
            import uvicorn
            use_fastapi = True
        except ImportError:
            if engine == "fastapi":
                print("❌ 錯誤: 已指定 --engine fastapi，但本機環境未安裝 fastapi/uvicorn。請先執行: pip install fastapi uvicorn")
                sys.exit(1)
            use_fastapi = False

    search_status_str = "已就緒 (Redis & Gemini Embedding 連線正常)" if search_use_case else f"未啟用 ({search_init_err or '未配置'})"

    print("=" * 64)
    print("⚡ 履歷轉檔與品管日誌 Web 查詢儀表板 (Conversion Dashboard)")
    print(f"• 服務網址: {url}")
    if use_fastapi:
        print(f"• 核心引擎: FastAPI + Uvicorn (業界主流 ASGI)")
        print(f"• Swagger:  {docs_url}")
        print(f"• ReDoc:    {redoc_url}")
    else:
        print("• 核心引擎: Python 內建 ThreadingHTTPServer (零外部相依模式)")
    print(f"• 語意檢索: {search_status_str}")
    print(f"• 稽核紀錄: {audit_path.resolve() if audit_path.exists() else f'{audit_path} (待建立)'}")
    print(f"• 系統日誌: {log_path.resolve() if log_path.exists() else f'{log_path} (待建立)'}")
    print("• 按 Ctrl+C 結束 Web 服務")
    print("=" * 64)

    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if use_fastapi:
        from src.interfaces.web.fastapi_server import run_fastapi_server
        from src.interfaces.web.server import build_chat_use_case

        chat_use_case, chat_init_err = build_chat_use_case(config, search_use_case)
        chat_status = "已就緒" if chat_use_case else f"未啟用 ({chat_init_err})"
        print(f"• 招募助手: {chat_status}")
        run_fastapi_server(use_case=use_case, search_use_case=search_use_case, host=host, port=port,
                           chat_use_case=chat_use_case)
    else:
        server = DashboardServer(use_case=use_case, search_use_case=search_use_case, host=host, port=port)
        server.start(blocking=True)


def __getattr__(name: str):
    """支援 `uvicorn web_dashboard:app --reload` 直接啟動"""
    if name == "app":
        from src.interfaces.web.fastapi_server import create_default_app
        return create_default_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()
