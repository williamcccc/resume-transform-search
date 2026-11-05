#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
履歷語意向量檢索 CLI 工具 (支援自然語言查詢、技術標籤過濾、區段篩選與互動模式)
"""
import argparse
import sys
from typing import List

# 確保 Windows 終端輸出 UTF-8 編碼，避免 CP950 亂碼
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.application.search_resumes_use_case import SearchResumesUseCase
from src.domain.models import SearchQuery, SearchResultItem
from src.infrastructure.config import AppConfig
from src.infrastructure.embeddings.gemini_embedding import GeminiEmbeddingService
from src.infrastructure.logging import setup_logging
from src.infrastructure.stores.redis_vector_store import RedisVectorStore


def parse_args():
    parser = argparse.ArgumentParser(
        description="依自然語言需求在 Redis 中進行履歷切片語意檢索 (支援 HNSW 向量搜尋 + Tag 混合過濾)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
範例用法:
  # 1. 基本自然語言檢索
  python search_resumes.py "熟悉分散式微服務架構與 High Traffic 高並發處理的後端"

  # 2. 限制只看「工作經歷」區塊，並指定技術標籤
  python search_resumes.py "設計過金流串接系統" --type experience --skills golang,redis

  # 3. 指定回傳前 10 筆最相關切片，並依求職者整合呈現
  python search_resumes.py "AWS 雲端架構設計與 Kubernetes 容器化" --top 10 --group

  # 4. 啟動終端機互動式問答檢索
  python search_resumes.py
""",
    )
    parser.add_argument("query", nargs="?", help="自然語言查詢條件 (若未填寫則進入終端互動模式)")
    parser.add_argument("--top", type=int, default=None, help="回傳最相關切片數量 (預設讀取 SEARCH_DEFAULT_TOP_K 或 5)")
    parser.add_argument(
        "--skills",
        help="技術標籤過濾 (以逗號分隔，例如: 'python,redis,fastapi')",
    )
    parser.add_argument(
        "--type",
        choices=["profile", "experience", "skills", "education", "project", "other"],
        help="限制搜尋的區塊類型",
    )
    parser.add_argument(
        "--group",
        action="store_true",
        help="將切片依求職者整合分組顯示",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="最低語意相似度門檻 (預設讀取 SEARCH_MIN_SCORE 或 0.0，低於此值將被過濾)",
    )
    parser.add_argument(
        "--redis-url",
        help="指定 Redis 連線字串 (預設讀取 .env 或 redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--api-key",
        help="指定 Gemini API Key (可選，預設讀取 .env)",
    )
    return parser.parse_args()


def display_results(results: List[SearchResultItem]):
    if not results:
        print("\n[!] 查無符合條件的履歷切片。請嘗試放寬查詢條件或確認 Redis 已建立索引。")
        return

    print(f"\n共找到 {len(results)} 筆高度相關的履歷切片：")
    print("=" * 70)

    for idx, item in enumerate(results, 1):
        sim_pct = f"{item.score * 100:.1f}%"
        skills_str = ", ".join(item.skills) if item.skills else "無特定標籤"
        meta_info = []
        if item.company:
            meta_info.append(f"任職公司: {item.company}")
        if item.job_title:
            meta_info.append(f"職稱: {item.job_title}")
        meta_str = f" ({' | '.join(meta_info)})" if meta_info else ""

        print(f"#{idx} 【相似度: {sim_pct}】 候選人: {item.candidate_name} [{item.candidate_id}]")
        print(f"   區段類型: {item.chunk_type.upper()} | 標題: {item.section_title}{meta_str}")
        print(f"   技術標籤: {skills_str}")
        if item.file_path:
            print(f"   來源檔案: {item.file_path}")
        print("   --- 內文摘要 ---")

        # 顯示內文前 5 行，其餘摺疊
        lines = item.content.strip().splitlines()
        preview_lines = lines[:5]
        for l in preview_lines:
            print(f"   > {l}")
        if len(lines) > 5:
            print(f"   > ... (共 {len(lines)} 行)")
        print("-" * 70)


def display_grouped_results(grouped: list):
    if not grouped:
        print("\n[!] 查無符合條件的候選人。請嘗試放寬查詢條件。")
        return

    print(f"\n共篩選出 {len(grouped)} 位符合條件的候選人：")
    print("=" * 70)

    for idx, g in enumerate(grouped, 1):
        sim_pct = f"{g['max_score'] * 100:.1f}%"
        skills_str = ", ".join(g["all_skills"]) if g["all_skills"] else "無"
        print(f"#{idx} 候選人: {g['candidate_name']} ({g['candidate_id']}) - 最高相似度: {sim_pct}")
        print(f"   彙整技能: {skills_str}")
        if g.get("file_path"):
            print(f"   來源檔案: {g['file_path']}")
        print(f"   匹配切片數: {len(g['matched_chunks'])}")

        for c_idx, c in enumerate(g["matched_chunks"], 1):
            sub_sim = f"{c.score * 100:.1f}%"
            print(f"     [{c_idx}] 相似度: {sub_sim} | {c.chunk_type} - {c.section_title}")
        print("-" * 70)


def execute_search(
    use_case: SearchResumesUseCase,
    query_text: str,
    args,
    default_top_k: int = 5,
    default_min_score: float = 0.0,
):
    skills_list = [s.strip().lower() for s in args.skills.split(",") if s.strip()] if args.skills else []
    active_top = args.top if args.top is not None else default_top_k
    active_min_score = args.min_score if args.min_score is not None else default_min_score
    query = SearchQuery(
        query_text=query_text,
        top_k=active_top,
        chunk_type=args.type,
        skills_filter=skills_list,
        min_score=active_min_score,
    )

    print(f"\n[檢索中] 查詢語句: '{query_text}'")
    if args.type:
        print(f"[篩選] 區段類型: {args.type}")
    if skills_list:
        print(f"[篩選] 必要技能: {', '.join(skills_list)}")
    if active_min_score > 0.0:
        print(f"[篩選] 最低相似度門檻: {active_min_score:.2f}")

    if args.group:
        grouped = use_case.execute_grouped_by_candidate(query)
        display_grouped_results(grouped)
    else:
        results = use_case.execute(query)
        display_results(results)


def main():
    args = parse_args()
    config = AppConfig.load(
        override_api_key=args.api_key,
        override_redis_url=args.redis_url,
    )
    setup_logging(config)

    if not config.gemini_api_key:
        print("[錯誤] 未設定 GEMINI_API_KEY，無法取得查詢向量。請於 .env 設定。")
        return 1

    try:
        embedding_service = GeminiEmbeddingService(
            api_key=config.gemini_api_key,
            model_name=config.embedding_model,
            dim=config.embedding_dim,
            max_retries=config.api_max_retries,
            retry_delay=config.api_retry_delay,
        )
        vector_store = RedisVectorStore(
            redis_url=config.redis_url,
            index_name=config.redis_index_name,
            prefix=config.redis_prefix,
            hash_prefix=config.redis_hash_prefix,
            hnsw_m=config.redis_hnsw_m,
            hnsw_ef_construction=config.redis_hnsw_ef_construction,
            hnsw_initial_cap=config.redis_hnsw_initial_cap,
            distance_metric=config.redis_distance_metric,
        )
        use_case = SearchResumesUseCase(
            embedding_service=embedding_service,
            vector_store=vector_store,
        )

        if args.query:
            execute_search(
                use_case,
                args.query,
                args,
                default_top_k=config.search_default_top_k,
                default_min_score=config.search_min_score,
            )
            return 0

        # 互動式查詢模式
        print("=" * 60)
        print("【履歷語意向量檢索 - 互動終端模式】")
        print("輸入自然語言描述需求 (例如: '三年以上 Go 後端，具備大型高流量架構經驗')")
        print("輸入 'exit' 或 'quit' 結束。")
        print("=" * 60)

        while True:
            try:
                user_input = input("\n請輸入檢索條件 > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("感謝使用，再見！")
                    break
                execute_search(
                    use_case,
                    user_input,
                    args,
                    default_top_k=config.search_default_top_k,
                    default_min_score=config.search_min_score,
                )
            except (KeyboardInterrupt, EOFError):
                print("\n檢索已中斷。")
                break

        return 0

    except Exception as e:
        print(f"\n[錯誤] 檢索失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
