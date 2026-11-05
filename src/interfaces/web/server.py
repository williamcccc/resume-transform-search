import json
import logging
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

from src.application.dashboard_use_case import GetDashboardDataUseCase
from src.application.dto import DashboardQueryDTO, WebSearchRequestDTO
from src.application.search_resumes_use_case import SearchResumesUseCase
from src.infrastructure.config import AppConfig
from src.infrastructure.readers.csv_audit_reader import CsvAuditLogReader
from src.infrastructure.readers.file_log_reader import FileAppLogReader

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD_HTML_PATH = STATIC_DIR / "dashboard.html"


def build_web_use_cases(
    config: Optional[AppConfig] = None,
) -> Tuple[GetDashboardDataUseCase, Optional[SearchResumesUseCase], Optional[Exception]]:
    """
    組裝 Web 儀表板與智能履歷檢索所需之 Use Case 實例 (Dependency Injection Bootstrap)。
    當向量檢索服務初始化失敗時自動優雅降級，不阻斷儀表板核心服務啟動。
    """
    active_config = config or AppConfig.load()
    audit_path = Path(active_config.default_audit_report or "logs/audit_report.csv")
    log_path = Path(active_config.log_file or "logs/app.log")

    audit_reader = CsvAuditLogReader()
    log_reader = FileAppLogReader()
    use_case = GetDashboardDataUseCase(
        audit_reader=audit_reader,
        system_log_reader=log_reader,
        csv_path=audit_path,
        log_path=log_path,
    )

    search_use_case: Optional[SearchResumesUseCase] = None
    search_init_err: Optional[Exception] = None
    try:
        from src.infrastructure.embeddings.gemini_embedding import GeminiEmbeddingService
        from src.infrastructure.stores.redis_vector_store import RedisVectorStore
        from src.infrastructure.parsers.experience_parser import RegexExperienceParser

        embedding_svc = GeminiEmbeddingService(
            api_key=active_config.gemini_api_key,
            model_name=active_config.embedding_model,
            dim=active_config.embedding_dim,
            batch_size=active_config.embedding_batch_size,
            max_retries=active_config.api_max_retries,
            retry_delay=active_config.api_retry_delay,
        )
        vector_store = RedisVectorStore(
            redis_url=active_config.redis_url,
            index_name=active_config.redis_index_name,
            prefix=active_config.redis_prefix,
            hash_prefix=active_config.redis_hash_prefix,
            hnsw_m=active_config.redis_hnsw_m,
            hnsw_ef_construction=active_config.redis_hnsw_ef_construction,
            hnsw_initial_cap=active_config.redis_hnsw_initial_cap,
            distance_metric=active_config.redis_distance_metric,
        )
        search_use_case = SearchResumesUseCase(
            embedding_service=embedding_svc,
            vector_store=vector_store,
            markdown_base_dir=Path(active_config.default_output_dir or "data/markdown_out"),
            experience_parser=RegexExperienceParser(),
        )
    except Exception as err:
        search_init_err = err
        logger.warning(f"履歷語意檢索服務初始化略過 (若無需搜尋履歷可忽略): {err}")

    return use_case, search_use_case, search_init_err


def make_dashboard_handler(
    use_case: GetDashboardDataUseCase,
    search_use_case: Optional[SearchResumesUseCase] = None,
):
    """建立綁定 Use Case 實例之 HTTP 請求處理器類別"""

    class DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # 抑制控制台流水帳請求日誌，僅在 DEBUG 時記錄
            logger.debug(f"{self.address_string()} - {format % args}")

        def do_GET(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_params = parse_qs(parsed_url.query)

            # 1. 根目錄與靜態 HTML 儀表板
            if path in ("/", "/index.html"):
                self.serve_dashboard_html()
                return

            # 2. API: 統計摘要
            if path == "/api/stats":
                self.handle_api_stats()
                return

            # 3. API: 轉檔稽核紀錄
            if path == "/api/audit":
                self.handle_api_audit(query_params)
                return

            # 4. API: 系統技術日誌
            if path == "/api/logs":
                self.handle_api_logs(query_params)
                return

            # 5. API: 履歷自然語言與制式搜尋
            if path == "/api/search":
                self.handle_api_search(query_params)
                return

            # 6. API: 履歷原文安全讀取
            if path == "/api/resume":
                self.handle_api_resume(query_params)
                return

            # 7. 404 Not Found
            self.send_error_response(404, "頁面或端點不存在")

        def serve_dashboard_html(self):
            if not DASHBOARD_HTML_PATH.exists():
                self.send_error_response(500, "Dashboard HTML 模板不存在")
                return

            try:
                with open(DASHBOARD_HTML_PATH, "r", encoding="utf-8") as f:
                    content = f.read()

                content_bytes = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content_bytes)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content_bytes)
            except Exception as err:
                logger.error(f"渲染 Dashboard 失敗: {err}")
                self.send_error_response(500, f"無法讀取儀表板: {str(err)}")

        def handle_api_stats(self):
            try:
                result = use_case.execute(DashboardQueryDTO(limit=1, max_log_lines=1))
                payload = asdict(result.summary)
                self.send_json_response(200, payload)
            except Exception as err:
                logger.error(f"取得統計 API 異常: {err}")
                self.send_error_response(500, str(err))

        def handle_api_audit(self, params: dict):
            try:
                status = params.get("status", [None])[0]
                search = params.get("search", [None])[0]
                
                try:
                    limit = min(int(params.get("limit", [50])[0]), 500)
                except ValueError:
                    limit = 50

                try:
                    offset = max(0, int(params.get("offset", [0])[0]))
                except ValueError:
                    offset = 0

                query = DashboardQueryDTO(
                    status=status,
                    search=search,
                    limit=limit,
                    offset=offset,
                    max_log_lines=1
                )
                result = use_case.execute(query)

                payload = {
                    "total": result.total_audit_records,
                    "offset": offset,
                    "limit": limit,
                    "items": [asdict(r) for r in result.audit_records]
                }
                self.send_json_response(200, payload)
            except Exception as err:
                logger.error(f"取得稽核紀錄 API 異常: {err}")
                self.send_error_response(500, str(err))

        def handle_api_logs(self, params: dict):
            try:
                level = params.get("level", [None])[0]
                search = params.get("search", [None])[0]

                try:
                    limit = min(int(params.get("limit", [100])[0]), 1000)
                except ValueError:
                    limit = 100

                query = DashboardQueryDTO(
                    log_level=level,
                    log_search=search,
                    limit=1,
                    max_log_lines=limit
                )
                result = use_case.execute(query)

                payload = {
                    "total": result.total_log_records,
                    "limit": limit,
                    "logs": [asdict(l) for l in result.recent_logs]
                }
                self.send_json_response(200, payload)
            except Exception as err:
                logger.error(f"取得日誌 API 異常: {err}")
                self.send_error_response(500, str(err))

        def handle_api_search(self, params: dict):
            if not search_use_case:
                self.send_error_response(503, "履歷檢索服務未初始化")
                return

            try:
                query_text = params.get("query", [""])[0]
                if not query_text:
                    self.send_error_response(400, "缺少必要參數: query")
                    return

                min_years_raw = params.get("min_years", [None])[0]
                min_years = float(min_years_raw) if min_years_raw and min_years_raw.strip() else None

                skills_raw = params.get("skills", [None])[0]
                skills_list = [s.strip().lower() for s in skills_raw.split(",") if s.strip()] if skills_raw else []

                chunk_type = params.get("chunk_type", [None])[0]

                try:
                    min_score = float(params.get("min_score", [0.5])[0])
                except ValueError:
                    min_score = 0.5

                try:
                    top_k = min(int(params.get("top_k", [20])[0]), 100)
                except ValueError:
                    top_k = 20

                group_by_cand = params.get("group_by_candidate", ["true"])[0].lower() in ("true", "1")

                if not query_text:
                    self.send_error_response(400, "query 參數不可為空")
                    return

                req_dto = WebSearchRequestDTO(
                    query_text=query_text,
                    min_years=min_years,
                    skills=skills_list,
                    chunk_type=chunk_type,
                    min_score=min_score,
                    top_k=top_k,
                    group_by_candidate=group_by_cand,
                )

                res = search_use_case.execute_web_search(req_dto)
                payload = {
                    "success": True,
                    "total_candidates": res.total_candidates,
                    "total_matched_chunks": res.total_chunks,
                    "total_chunks": res.total_chunks,
                    "query_text": res.query_text,
                    "candidates": [
                        {
                            "candidate_id": c.candidate_id,
                            "candidate_name": c.candidate_name,
                            "max_similarity": c.max_score,
                            "parsed_years": c.years_of_experience,
                            "raw_experience": c.experience_raw,
                            "skills": c.all_skills,
                            "total_chunks": len(c.matched_chunks),
                            "matched_chunks": [
                                {
                                    "chunk_id": getattr(ch, "chunk_id", idx),
                                    "chunk_type": ch.chunk_type,
                                    "section_title": ch.section_title,
                                    "content": ch.content,
                                    "similarity": ch.score,
                                    "score": ch.score,
                                    "skills": ch.skills,
                                }
                                for idx, ch in enumerate(c.matched_chunks)
                            ]
                        }
                        for c in res.candidates
                    ],
                    "items": [
                        {
                            "candidate_id": ch.candidate_id,
                            "candidate_name": ch.candidate_name,
                            "chunk_type": ch.chunk_type,
                            "section_title": ch.section_title,
                            "content": ch.content,
                            "similarity": ch.score,
                            "score": ch.score,
                            "skills": ch.skills,
                        }
                        for ch in res.raw_chunks
                    ],
                    "raw_chunks": [asdict(c) for c in res.raw_chunks],
                }
                self.send_json_response(200, payload)
            except Exception as err:
                logger.error(f"履歷檢索 API 異常: {err}")
                self.send_error_response(500, str(err))

        def handle_api_resume(self, params: dict):
            if not search_use_case:
                self.send_error_response(503, "履歷檢索服務未初始化")
                return

            candidate_id = params.get("candidate_id", [""])[0]
            if not candidate_id:
                self.send_error_response(400, "缺少必要參數: candidate_id")
                return

            if ".." in candidate_id or "/" in candidate_id or "\\" in candidate_id:
                self.send_error_response(400, f"非法候選人識別碼 [{candidate_id}] (包含特殊路徑字元)")
                return

            md = search_use_case.get_resume_markdown(candidate_id)
            if md is None:
                self.send_error_response(404, f"找不到候選人 [{candidate_id}] 之履歷檔案")
                return

            self.send_json_response(200, {
                "success": True,
                "candidate_id": candidate_id,
                "markdown": md,
            })

        def send_json_response(self, status_code: int, data: dict):
            json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(json_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json_bytes)

        def send_error_response(self, status_code: int, message: str):
            payload = {"error": message, "status": status_code}
            self.send_json_response(status_code, payload)

    return DashboardHandler


class DashboardServer:
    """
    輕量化 Web 儀表板 HTTP 伺服器
    基於標準庫 ThreadingHTTPServer 實作，支援多執行緒並發與優雅關閉
    """

    def __init__(
        self,
        use_case: GetDashboardDataUseCase,
        search_use_case: Optional[SearchResumesUseCase] = None,
        host: str = "127.0.0.1",
        port: int = 8080,
    ):
        self.host = host
        handler_cls = make_dashboard_handler(use_case, search_use_case)
        self.server = ThreadingHTTPServer((self.host, port), handler_cls)
        self.port = self.server.server_address[1]
        self.use_case = use_case
        self.search_use_case = search_use_case
        self._thread: Optional[threading.Thread] = None

    def start(self, blocking: bool = True):
        """啟動 Web 服務"""
        logger.info(f"⚡ 轉檔 Web 儀表板已啟動: http://{self.host}:{self.port}")
        if blocking:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                logger.info("接收到中斷訊號，正在關閉 Web 伺服器...")
            finally:
                self.stop()
        else:
            self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._thread.start()

    def stop(self):
        """關閉 Web 服務並釋放 Port"""
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception as err:
            logger.warning(f"關閉 Web 伺服器時產生例外: {err}")
