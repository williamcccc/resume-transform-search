import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.application.dashboard_use_case import GetDashboardDataUseCase
from src.application.dto import DashboardQueryDTO, WebSearchRequestDTO
from src.application.search_resumes_use_case import SearchResumesUseCase
from src.infrastructure.config import AppConfig
from src.interfaces.web.server import build_web_use_cases

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD_HTML_PATH = STATIC_DIR / "dashboard.html"


def create_app(
    use_case: GetDashboardDataUseCase,
    search_use_case: Optional[SearchResumesUseCase] = None,
) -> FastAPI:
    """
    建立 FastAPI 應用實例
    配置 OpenAPI 文檔標籤、CORS 中介軟體、品管統計 API 與履歷語意檢索 API
    """
    app = FastAPI(
        title="文件轉檔與品管日誌儀表板 API - 履歷智能檢索",
        description="提供履歷文件轉檔品管監控、自然語言語意向量搜尋與工作年資/技術標籤複合過濾端點",
        version="1.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 啟用 CORS 跨來源支援
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/redocs", include_in_schema=False)
    async def redirect_redocs():
        """容錯重導向：支援 /redocs 重導至標準 /redoc"""
        return RedirectResponse(url="/redoc", status_code=307)

    @app.get("/doc", include_in_schema=False)
    async def redirect_doc():
        """容錯重導向：支援 /doc 重導至標準 /docs"""
        return RedirectResponse(url="/docs", status_code=307)

    @app.get(
        "/",
        response_class=HTMLResponse,
        summary="取得單頁視覺化儀表板 (Dashboard SPA)",
        tags=["UI 頁面"],
    )
    async def serve_dashboard():
        if not DASHBOARD_HTML_PATH.exists():
            raise HTTPException(status_code=500, detail="Dashboard HTML 模板不存在")
        try:
            with open(DASHBOARD_HTML_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content, status_code=200)
        except Exception as err:
            logger.error(f"讀取 Dashboard 樣板失敗: {err}")
            raise HTTPException(status_code=500, detail=str(err)) from err

    @app.get(
        "/api/stats",
        summary="取得轉檔統計摘要指標",
        description="即時聚合全歷次累計之總檔數、成功數、隔離數、錯誤數、成功率與平均評分",
        tags=["統計指標 API"],
    )
    async def get_stats():
        try:
            result = use_case.execute(DashboardQueryDTO(limit=1, max_log_lines=1))
            return asdict(result.summary)
        except Exception as err:
            logger.error(f"取得統計失敗: {err}")
            raise HTTPException(status_code=500, detail=str(err)) from err

    @app.get(
        "/api/audit",
        summary="查詢轉檔品管稽核紀錄清單",
        description="分頁查詢轉檔歷史紀錄，支援依狀態 (SUCCESS/QUARANTINE/ERROR) 與關鍵字篩選",
        tags=["品管稽核 API"],
    )
    async def get_audit(
        status: Optional[str] = Query(None, description="篩選狀態: SUCCESS, QUARANTINE, ERROR, ALL"),
        search: Optional[str] = Query(None, description="檔名、警示或模型關鍵字搜尋"),
        limit: int = Query(50, ge=1, le=500, description="每頁筆數限制 (1~500)"),
        offset: int = Query(0, ge=0, description="分頁起始位移 (Offset)"),
    ):
        try:
            query = DashboardQueryDTO(
                status=status,
                search=search,
                limit=limit,
                offset=offset,
                max_log_lines=1,
            )
            result = use_case.execute(query)
            return {
                "total": result.total_audit_records,
                "offset": offset,
                "limit": limit,
                "items": [asdict(r) for r in result.audit_records],
            }
        except Exception as err:
            logger.error(f"取得稽核紀錄失敗: {err}")
            raise HTTPException(status_code=500, detail=str(err)) from err

    @app.get(
        "/api/logs",
        summary="查詢系統技術日誌 (App Logs)",
        description="即時檢索系統 app.log 日誌，支援等級 (INFO/WARNING/ERROR) 與文字搜尋",
        tags=["技術日誌 API"],
    )
    async def get_logs(
        level: Optional[str] = Query(None, description="日誌等級過濾: INFO, WARNING, ERROR, ALL"),
        search: Optional[str] = Query(None, description="日誌訊息或模組關鍵字"),
        limit: int = Query(100, ge=1, le=1000, description="回傳日誌最大行數 (1~1000)"),
    ):
        try:
            query = DashboardQueryDTO(
                log_level=level,
                log_search=search,
                limit=1,
                max_log_lines=limit,
            )
            result = use_case.execute(query)
            return {
                "total": result.total_log_records,
                "limit": limit,
                "logs": [asdict(l) for l in result.recent_logs],
            }
        except Exception as err:
            logger.error(f"取得日誌失敗: {err}")
            raise HTTPException(status_code=500, detail=str(err)) from err

    # ==========================================
    # 履歷自然語言與制式條件智能檢索 API
    # ==========================================

    @app.get(
        "/api/search",
        summary="自然語言與制式條件履歷檢索 (GET)",
        description="支援自然語言語意向量搜尋 (768 維 KNN)，並複合最低工作年資、技術標籤與區塊類型過濾",
        tags=["履歷智能檢索 API"],
    )
    async def search_resumes_get(
        query: str = Query(..., description="自然語言查詢條件 (如: 熟悉微服務與高並發架構的後端)"),
        min_years: Optional[float] = Query(None, description="最低工作年資限制 (如: 3 代表 3 年以上)"),
        skills: Optional[str] = Query(None, description="必備技術標籤 (以逗號分隔，如: python,redis,docker)"),
        chunk_type: Optional[str] = Query(None, description="區塊類型限制: experience, skills, profile 等"),
        min_score: float = Query(0.5, ge=0.0, le=1.0, description="最低語意相似度門檻 (預設 0.5)"),
        top_k: int = Query(20, ge=1, le=100, description="最大檢索切片數 (預設 20)"),
        group_by_candidate: bool = Query(True, description="是否依求職候選人整合顯示"),
    ):
        if not search_use_case:
            raise HTTPException(status_code=503, detail="履歷檢索服務未初始化 (未配置 Redis 或 Embedding 服務)")

        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="query 參數不可為空")

        skills_list = [s.strip().lower() for s in skills.split(",") if s.strip()] if skills else []
        req_dto = WebSearchRequestDTO(
            query_text=query.strip(),
            min_years=min_years,
            skills=skills_list,
            chunk_type=chunk_type,
            min_score=min_score,
            top_k=top_k,
            group_by_candidate=group_by_candidate,
        )

        try:
            res = search_use_case.execute_web_search(req_dto)
            return {
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
        except Exception as err:
            logger.error(f"履歷語意檢索失敗: {err}")
            raise HTTPException(status_code=500, detail=str(err)) from err

    @app.get(
        "/api/resume",
        summary="讀取候選人完整 Markdown 履歷全文",
        description="依 candidate_id 安全讀取 Markdown 履歷原文以供前端 Modal 預覽，防範路徑遍歷",
        tags=["履歷智能檢索 API"],
    )
    async def get_resume_content(
        candidate_id: str = Query(..., description="求職者識別碼 (例如: 王小明_BE)"),
    ):
        if not search_use_case:
            raise HTTPException(status_code=503, detail="履歷檢索服務未初始化")

        if not candidate_id or ".." in candidate_id or "/" in candidate_id or "\\" in candidate_id:
            raise HTTPException(status_code=400, detail=f"非法候選人識別碼 [{candidate_id}] (包含特殊路徑字元)")

        md_content = search_use_case.get_resume_markdown(candidate_id)
        if md_content is None:
            raise HTTPException(status_code=404, detail=f"找不到候選人 [{candidate_id}] 之履歷檔案")

        return {
            "success": True,
            "candidate_id": candidate_id,
            "markdown": md_content,
        }

    return app


def create_default_app(config: Optional[AppConfig] = None) -> FastAPI:
    """
    標準 ASGI Application Factory：
    自動載入 AppConfig 並組裝 Use Cases，支援 uvicorn --factory 直接啟動：
    uvicorn src.interfaces.web.fastapi_server:create_default_app --factory --reload
    """
    active_config = config or AppConfig.load()
    use_case, search_use_case, _ = build_web_use_cases(active_config)
    return create_app(use_case=use_case, search_use_case=search_use_case)


_default_app: Optional[FastAPI] = None


def __getattr__(name: str) -> Any:
    """
    PEP 562 模組層級延遲屬性載入：
    支援 `uvicorn src.interfaces.web.fastapi_server:app --reload` 直接啟動，
    同時避免在單元測試僅匯入 `create_app` 時觸發多餘的預設依賴初始化。
    """
    global _default_app
    if name == "app":
        if _default_app is None:
            _default_app = create_default_app()
        return _default_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run_fastapi_server(
    use_case: GetDashboardDataUseCase,
    search_use_case: Optional[SearchResumesUseCase] = None,
    host: str = "127.0.0.1",
    port: int = 8080,
):
    """啟動 FastAPI + Uvicorn 伺服器"""
    app = create_app(use_case, search_use_case)
    logger.info(f"🚀 FastAPI 伺服器已啟動: http://{host}:{port}")
    logger.info(f"📖 Swagger 互動式 API 文檔: http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="warning")
