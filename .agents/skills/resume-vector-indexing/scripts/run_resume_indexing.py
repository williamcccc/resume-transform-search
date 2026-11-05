#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_resume_indexing.py
-----------------------
輔助執行腳本：智能路徑解析、預檢與履歷向量入庫調度器。
自動探測 resume/markdown_out 或 data/markdown_out，並調用 index_to_redis.py。
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# 確保 Windows 終端輸出 UTF-8 編碼
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[4]


def resolve_markdown_dir(preferred_path: str = None) -> Path:
    """自動解析目標 Markdown 履歷目錄"""
    candidates = []
    if preferred_path:
        candidates.append(Path(preferred_path))
        candidates.append(ROOT_DIR / preferred_path)

    # 預設候選目錄 (包含 resume/markdown_out 與 data/markdown_out)
    candidates.extend([
        ROOT_DIR / "resume" / "markdown_out",
        ROOT_DIR / "data" / "markdown_out",
        Path("resume/markdown_out"),
        Path("data/markdown_out"),
    ])

    for c in candidates:
        if c.exists() and c.is_dir():
            md_files = list(c.rglob("*.md"))
            if md_files:
                return c.resolve()

    # 若未找到包含 md 的目錄，回傳最合理的預設路徑以利報錯提示
    return (ROOT_DIR / "data" / "markdown_out").resolve()


def check_prerequisites(redis_url: str = None) -> tuple[bool, str]:
    """檢查 Redis 與 API Key 等前置條件"""
    env_file = ROOT_DIR / ".env"
    api_key = os.environ.get("GEMINI_API_KEY", "")
    r_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    if not api_key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif not redis_url and line.startswith("REDIS_URL="):
                r_url = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not api_key:
        return False, "未檢測到 GEMINI_API_KEY，請於 .env 設定或帶入 --api-key 引數。"

    # 嘗試測試 Redis 連線 (非阻斷性快速測試)
    try:
        import redis
        client = redis.from_url(r_url, socket_timeout=2)
        client.ping()
    except Exception as e:
        return False, f"無法連線至 Redis 節點 ({r_url})，錯誤: {e}\n請確認 Redis 伺服器是否已啟動。"

    return True, ""


def main():
    parser = argparse.ArgumentParser(
        description="履歷 Markdown 自動探測與向量化入庫調度工具",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="欲索引之 Markdown 履歷目錄或檔案 (預設自動偵測 resume/markdown_out 或 data/markdown_out)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="重建 RediSearch 向量索引",
    )
    parser.add_argument(
        "--redis-url",
        help="指定 Redis 連線位址",
    )
    parser.add_argument(
        "--api-key",
        help="指定 Gemini API Key",
    )
    parser.add_argument(
        "--model",
        help="指定 Embedding 模型",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="限制處理之 Markdown 檔案數量上限 (例如: --limit 10)",
    )
    parser.add_argument(
        "--skip-precheck",
        action="store_true",
        help="略過前置連線與金鑰檢驗",
    )


    args = parser.parse_args()

    target_dir = resolve_markdown_dir(args.path)
    if not target_dir.exists():
        print(f"[錯誤] 找不到目標目錄: {target_dir}")
        print("請確認 resume/markdown_out 或 data/markdown_out 目錄存在且包含 .md 檔案。")
        return 1

    md_files = list(target_dir.rglob("*.md"))
    if not md_files:
        print(f"[警告] 目錄 '{target_dir}' 下無任何 .md 檔案。")
        return 1

    print("=" * 65)
    print("🚀 [Skill] 履歷語意向量化入庫調度器")
    print(f"- 目標目錄: {target_dir}")
    print(f"- 探索到 Markdown 檔案數: {len(md_files)} 份")
    if args.limit:
        print(f"- 限制處理筆數: {args.limit} 份")
    print(f"- 重建索引: {'是' if args.recreate else '否'}")
    print("=" * 65)

    if not args.skip_precheck:
        ok, msg = check_prerequisites(args.redis_url)
        if not ok:
            print(f"[前置檢查失敗] {msg}")
            return 1
        print("✅ [前置檢查通過] Redis 連線正常，GEMINI_API_KEY 已就緒。")

    # 組裝 index_to_redis.py 指令
    entrypoint = ROOT_DIR / "index_to_redis.py"
    cmd = [sys.executable, str(entrypoint), str(target_dir)]
    if args.recreate:
        cmd.append("--recreate")
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    if args.redis_url:
        cmd.extend(["--redis-url", args.redis_url])
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    if args.model:
        cmd.extend(["--model", args.model])


    print(f"\n[執行指令] {' '.join(cmd)}\n")
    proc = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
