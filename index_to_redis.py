#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
履歷 Markdown 語意切片、文本向量化與 Redis 索引建置 CLI 工具
"""
import argparse
from pathlib import Path
import sys

# 確保 Windows 終端輸出 UTF-8 編碼，避免 CP950 亂碼
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.application.dto import IndexCommand
from src.application.index_resumes_use_case import IndexResumesUseCase
from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker
from src.infrastructure.config import AppConfig
from src.infrastructure.embeddings.gemini_embedding import GeminiEmbeddingService
from src.infrastructure.logging import setup_logging
from src.infrastructure.stores.redis_vector_store import RedisVectorStore


def parse_args():
    parser = argparse.ArgumentParser(
        description="將履歷 Markdown 檔案進行語意結構化切片、Embedding 向量化並存入 Redis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
範例用法:
  # 1. 索引單一 Markdown 履歷檔案
  python index_to_redis.py "output_md/sample_resume.md"

  # 2. 批次索引目錄下所有 Markdown 履歷
  python index_to_redis.py output_md/

  # 3. 重建 Redis 索引 (清除原有索引重新建立)
  python index_to_redis.py output_md/ --recreate

  # 4. 指定自訂 Redis 連線位址
  python index_to_redis.py output_md/ --redis-url redis://localhost:6379/0
""",
    )
    parser.add_argument("path", help="要索引的 Markdown 檔案路徑或包含 Markdown 檔案的目錄路徑")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="重建 RediSearch 向量索引 (若索引已存在將重設)",
    )
    parser.add_argument(
        "--redis-url",
        help="指定 Redis 連線字串 (預設讀取 .env 或 redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--api-key",
        help="指定 Gemini API Key (可選，預設讀取 .env)",
    )
    parser.add_argument(
        "--model",
        help="指定 Embedding 模型 (預設 gemini-embedding-001)",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="限制處理之 Markdown 檔案數量上限 (例如: --limit 10)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="強制重新計算所有切片向量並更新，忽略內容 Hash 增量快取",
    )
    parser.add_argument(
        "--min-chunk-size",
        type=int,
        default=None,
        help="切片最小字元門檻，低於此值將觸發相鄰區塊語意合併 (預設讀取 MIN_CHUNK_SIZE 或 80)",
    )
    return parser.parse_args()



def main():
    args = parse_args()
    target_path = Path(args.path)

    if not target_path.exists():
        print(f"[錯誤] 找不到目標路徑: '{target_path}'")
        return 1

    config = AppConfig.load(
        override_api_key=args.api_key,
        override_redis_url=args.redis_url,
        override_embedding_model=args.model,
    )
    setup_logging(config)

    if not config.gemini_api_key:
        print("[錯誤] 未設定 GEMINI_API_KEY，無法呼叫向量化服務。請於 .env 設定或使用 --api-key 引數。")
        return 1

    # 若使用者未特別傳入 --min-chunk-size，則採用 config 預設值
    active_min_chunk_size = args.min_chunk_size if args.min_chunk_size is not None else config.min_chunk_size

    print("=" * 60)
    print("【履歷語意向量化與 Redis 入庫工具】")
    print(f"- 目標路徑: {target_path.resolve()}")
    print(f"- Redis 節點: {config.redis_url}")
    print(f"- 向量索引: {config.redis_index_name} (前綴: {config.redis_prefix})")
    print(f"- 向量模型: {config.embedding_model} (維度: {config.embedding_dim}，批次: {config.embedding_batch_size})")
    print(f"- 重建索引: {'是' if args.recreate else '否'}")
    print(f"- 強制更新: {'是' if args.force else '否 (啟用 Hash 增量比對)'}")
    print(f"- 切片大小區間: {active_min_chunk_size} ~ {config.max_chunk_size} 字元")
    print("=" * 60)

    try:
        chunker = MarkdownChunker(
            min_chunk_chars=active_min_chunk_size,
            max_chunk_chars=config.max_chunk_size,
            extra_skill_patterns=config.extra_skill_patterns,
        )
        embedding_service = GeminiEmbeddingService(
            api_key=config.gemini_api_key,
            model_name=config.embedding_model,
            dim=config.embedding_dim,
            batch_size=config.embedding_batch_size,
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

        use_case = IndexResumesUseCase(
            chunker=chunker,
            embedding_service=embedding_service,
            vector_store=vector_store,
        )

        if target_path.is_file():
            cmd = IndexCommand(
                file_path=target_path,
                recreate_index=args.recreate,
                limit=args.limit,
                force=args.force,
            )
        else:
            cmd = IndexCommand(
                dir_path=target_path,
                recreate_index=args.recreate,
                limit=args.limit,
                force=args.force,
            )

        print("[資訊] 正在解析 Markdown、產生語意切片並批次向量化中...")
        result = use_case.execute(cmd)

        print("\n" + "=" * 60)
        print("【入庫統計彙總】")
        print(f"- 總掃描 Markdown 檔數: {result.total_files}")
        print(f"- 成功處理檔案數: {result.indexed_files}")
        print(f"- 跳過未變更檔案數: {result.skipped_files} (Hash 比對一致)")
        print(f"- 總切片存入數量: {result.total_chunks}")

        if result.errors:
            print(f"- 發生錯誤數量: {len(result.errors)}")
            for err in result.errors:
                print(f"  [!] {err}")
            print("=" * 60)
            return 1

        print("=" * 60)
        print("[完成] 履歷切片向量化與 Redis 索引建置完成！您可以使用 search_resumes.py 開始檢索。")
        return 0

    except Exception as e:
        print(f"\n[致命錯誤] 索引執行失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
