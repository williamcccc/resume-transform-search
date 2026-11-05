#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件與履歷智慧轉 Markdown 工具 (CLI 啟動進入點)
採用 DDD (領域驅動設計) 架構拆分，完整支援 PDF、Word、智慧自動分流與兩階段自我審核。
"""
import sys

# 確保 Windows 終端輸出 UTF-8 編碼，避免 CP950 亂碼
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.interfaces.cli.runner import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
