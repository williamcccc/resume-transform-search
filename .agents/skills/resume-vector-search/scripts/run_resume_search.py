#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_resume_search.py
---------------------
輔助執行腳本：履歷語意向量檢索調度與預檢工具。
提供查詢參數結構化解析、前置連線檢測與調用 search_resumes.py。
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


def check_prerequisites(redis_url: str = None) -> tuple[bool, str]:
    """檢測 Redis 伺服器與 GEMINI_API_KEY 是否具備"""
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

    try:
        import redis
        client = redis.from_url(r_url, socket_timeout=2)
        client.ping()
    except Exception as e:
        return False, f"無法連線至 Redis 服務 ({r_url}): {e}\n請確認 Redis 伺服器是否已啟動。"

    return True, ""


def main():
    parser = argparse.ArgumentParser(
        description="履歷語意向量檢索調度工具",
    )
    parser.add_argument("query", nargs="?", help="自然語言查詢條件")
    parser.add_argument("-k", "--top", type=int, default=5, help="回傳切片數量上限 (預設 5)")
    parser.add_argument("--skills", help="技術標籤過濾 (以逗號分隔，如 'python,redis')")
    parser.add_argument(
        "--type",
        choices=["profile", "experience", "skills", "education", "project", "other"],
        help="限制搜尋的區段類型",
    )
    parser.add_argument("--group", action="store_true", help="依候選人歸併分組呈現")
    parser.add_argument("--redis-url", help="指定 Redis 連線位址")
    parser.add_argument("--api-key", help="指定 Gemini API Key")
    parser.add_argument("--skip-precheck", action="store_true", help="略過前置檢查")

    args = parser.parse_args()

    if not args.query:
        print("[提示] 未指定查詢語句，即將進入互動式終端檢索模式...")

    if not args.skip_precheck:
        ok, msg = check_prerequisites(args.redis_url)
        if not ok:
            print(f"[錯誤] {msg}")
            return 1

    entrypoint = ROOT_DIR / "search_resumes.py"
    cmd = [sys.executable, str(entrypoint)]

    if args.query:
        cmd.append(args.query)
    if args.top:
        cmd.extend(["--top", str(args.top)])
    if args.skills:
        cmd.extend(["--skills", args.skills])
    if args.type:
        cmd.extend(["--type", args.type])
    if args.group:
        cmd.append("--group")
    if args.redis_url:
        cmd.extend(["--redis-url", args.redis_url])
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])

    proc = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
