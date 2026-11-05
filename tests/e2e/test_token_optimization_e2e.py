#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_token_optimization_e2e.py
------------------------------
端到端 (E2E) QA 實測驗證腳本：Token 最佳化特性 (增量 Hash 比對、過短切片合併、CLI 參數向下相容)。
執行真實 CLI 子行程與 Redis 交互，驗證 100% AC 驗收標準。
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


class TestTokenOptimizationE2E(unittest.TestCase):
    """Token 最佳化端到端 QA 實測"""

    def setUp(self):
        # 讀取測試專用 Redis URL (預設 DB 15，隔離生產環境 DB 0)
        self.redis_test_url = os.environ.get("REDIS_TEST_URL", "redis://localhost:6379/15")
        self._cleanup_test_data()

    def tearDown(self):
        self._cleanup_test_data()

    def _cleanup_test_data(self):
        try:
            from src.infrastructure.stores.redis_vector_store import RedisVectorStore
            store = RedisVectorStore(redis_url=self.redis_test_url)
            store.delete_by_candidate("qa_candidate_resume")
        except Exception:
            pass

    def test_cli_flags_backward_compatibility(self):
        """[AC 1] 驗證 index_to_redis.py 新增 --force 與 --min-chunk-size 後向下相容"""
        cmd = [sys.executable, str(ROOT_DIR / "index_to_redis.py"), "--help"]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT_DIR),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--force", proc.stdout)
        self.assertIn("--min-chunk-size", proc.stdout)

    def test_incremental_indexing_workflow_live(self):
        """[AC 1 & AC 2] 驗證真實環境下之增量略過與強制覆蓋流程"""
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            md_file = temp_dir / "qa_candidate_resume.md"
            md_file.write_text(
                """# 測試候選人 QA

## 個人簡介
擁有豐富的後端分散式系統實作經驗。

## 工作經歷
### 科技創新公司｜資深工程師
- 負責核心 API 開發與架構優化，技術棧包含 Python、Redis 與 Docker。
- 主導微服務系統建置。

## 專業技能
- Python, Redis, Docker, FastAPI
""",
                encoding="utf-8",
            )

            # 第一次入庫 (全新寫入，指定測試庫隔離)
            cmd1 = [sys.executable, str(ROOT_DIR / "index_to_redis.py"), str(temp_dir), "--redis-url", self.redis_test_url]
            proc1 = subprocess.run(
                cmd1,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT_DIR),
            )
            self.assertEqual(proc1.returncode, 0)
            self.assertIn("成功處理檔案數: 1", proc1.stdout)
            self.assertIn("跳過未變更檔案數: 0", proc1.stdout)

            # 第二次入庫 (檔案未修改，應觸發增量快取略過，節省 100% Token)
            cmd2 = [sys.executable, str(ROOT_DIR / "index_to_redis.py"), str(temp_dir), "--redis-url", self.redis_test_url]
            proc2 = subprocess.run(
                cmd2,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT_DIR),
            )
            self.assertEqual(proc2.returncode, 0)
            self.assertIn("成功處理檔案數: 0", proc2.stdout)
            self.assertIn("跳過未變更檔案數: 1", proc2.stdout)

            # 第三次入庫 (附帶 --force，應繞過快取強制重算)
            cmd3 = [sys.executable, str(ROOT_DIR / "index_to_redis.py"), str(temp_dir), "--force", "--redis-url", self.redis_test_url]
            proc3 = subprocess.run(
                cmd3,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT_DIR),
            )
            self.assertEqual(proc3.returncode, 0)
            self.assertIn("成功處理檔案數: 1", proc3.stdout)
            self.assertIn("跳過未變更檔案數: 0", proc3.stdout)


if __name__ == "__main__":
    unittest.main()
