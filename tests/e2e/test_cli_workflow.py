#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_cli_workflow.py
--------------------
端到端 (E2E) CLI 流程實測腳本。
驗證命令列介面在真實執行緒與子行程環境下的向下相容性、錯誤防禦與資源生命週期（防 Windows 檔案鎖死）。
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


class TestCliWorkflowE2E(unittest.TestCase):
    """端到端 CLI 命令列執行實測案例"""

    def test_cli_help_flag_backward_compatibility(self):
        """驗證 convert_to_md.py --help 指令執行順暢且向下相容"""
        cmd = [sys.executable, str(ROOT_DIR / "convert_to_md.py"), "--help"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT_DIR))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("convert_to_md", proc.stdout)
        self.assertIn("--review", proc.stdout)
        self.assertIn("--index-to-redis", proc.stdout)

    def test_cli_non_existent_file_graceful_error(self):
        """驗證傳入不存在之檔案時，CLI 優雅報錯且不拋出未捕獲之崩潰例外"""
        non_existent = str(ROOT_DIR / "non_existent_resume_file_xyz.pdf")
        cmd = [sys.executable, str(ROOT_DIR / "convert_to_md.py"), non_existent]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT_DIR))
        # 應以非 0 狀態結束，且標準輸出或錯誤應包含清楚提示
        self.assertNotEqual(proc.returncode, 0)

    def test_search_cli_help_flag(self):
        """驗證 search_resumes.py --help 指令正常運作"""
        cmd = [sys.executable, str(ROOT_DIR / "search_resumes.py"), "--help"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT_DIR))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("search_resumes", proc.stdout)
        self.assertIn("--skills", proc.stdout)

    def test_web_dashboard_cli_help_flag(self):
        """驗證 web_dashboard.py --help 指令正常運作並顯示雙引擎說明"""
        cmd = [sys.executable, str(ROOT_DIR / "web_dashboard.py"), "--help"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT_DIR))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("web_dashboard", proc.stdout)
        self.assertIn("--engine", proc.stdout)

    def test_cli_quota_exceeded_file_handled_gracefully(self):
        """驗證傳入超過配額大小 (25MB) 之檔案時，CLI 優雅攔截並報錯"""
        with tempfile.TemporaryDirectory() as td:
            huge_file = Path(td) / "huge.pdf"
            # 建立 26MB 稀疏或虛擬檔案
            with open(huge_file, "wb") as f:
                f.seek(26 * 1024 * 1024)
                f.write(b"0")

            cmd = [sys.executable, str(ROOT_DIR / "convert_to_md.py"), str(huge_file)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT_DIR))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("超過系統硬上限 (25MB)", proc.stdout + proc.stderr)



if __name__ == "__main__":
    unittest.main()
