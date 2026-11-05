#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_doc_sync.py
------------------
自動驗證專案技術文檔、ADR 索引與需求規範的一致性。
檢查要點：
1. docs/adr/ 下的所有 ADR 是否 100% 登錄於 docs/adr/README.md 索引表。
2. ADR 編號是否符合連續編號格式 (XXXX-*.md)。
3. ADR 文件中狀態是否明確標註。
4. REQUIREMENTS.md 與 ARCHITECTURE.md 是否存在且未損毀。
"""

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
DOCS_DIR = ROOT_DIR / "docs"
DOCS_ADR_DIR = DOCS_DIR / "adr"
DOCS_SPECS_DIR = DOCS_DIR / "specs"
DOCS_QA_DIR = DOCS_DIR / "qa_reports"
DOCS_README = DOCS_DIR / "README.md"
ADR_README = DOCS_ADR_DIR / "README.md"
REQUIREMENTS_FILE = ROOT_DIR / "REQUIREMENTS.md"
ARCHITECTURE_FILE = ROOT_DIR / "ARCHITECTURE.md"


def check_basic_docs_exist() -> bool:
    all_ok = True
    for f in [REQUIREMENTS_FILE, ARCHITECTURE_FILE, ADR_README, DOCS_README]:
        if not f.exists() or f.stat().st_size == 0:
            print(f"[FAIL] 缺少必要核心文檔或文檔為空: {f.relative_to(ROOT_DIR)}")
            all_ok = False
        else:
            print(f"[PASS] 核心文檔存在且非空: {f.relative_to(ROOT_DIR)}")
    return all_ok


def check_directory_docs(dir_path: Path, doc_type_name: str, index_file: Path) -> bool:
    if not dir_path.exists():
        print(f"[FAIL] {doc_type_name} 目錄不存在: {dir_path.relative_to(ROOT_DIR)}")
        return False

    files = sorted([f for f in dir_path.glob("*.md") if f.name != "README.md"])
    if not files:
        print(f"[WARN] {doc_type_name} 目錄下未發現任何 Markdown 檔案: {dir_path.relative_to(ROOT_DIR)}")
        return True

    index_content = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    all_ok = True

    for p in files:
        match = re.match(r"^(\d{4})-(.+)\.md$", p.name)
        if not match:
            print(f"[FAIL] {doc_type_name} 檔名格式不符 (應為 4 位數字-kebab-case.md): {p.name}")
            all_ok = False
            continue

        if p.stat().st_size == 0:
            print(f"[FAIL] {doc_type_name} 檔案內容為空: {p.name}")
            all_ok = False

        if p.name not in index_content:
            print(f"[FAIL] {doc_type_name} 未登載於 {index_file.relative_to(ROOT_DIR)} 索引表: {p.name}")
            all_ok = False

    if all_ok:
        print(f"[PASS] 所有 {doc_type_name} ({len(files)} 個) 均已通過格式校驗並登載於索引表")
    return all_ok


def check_adr_sync() -> bool:
    if not DOCS_ADR_DIR.exists():
        print(f"[FAIL] docs/adr 目錄不存在: {DOCS_ADR_DIR}")
        return False

    adr_files = sorted([f for f in DOCS_ADR_DIR.glob("*.md") if f.name != "README.md"])
    if not adr_files:
        print("[WARN] docs/adr 目錄下未發現任何 ADR 檔案")
        return True

    readme_content = ADR_README.read_text(encoding="utf-8")
    all_ok = True

    # 1. 檢查檔案編號格式
    expected_num = 1
    for adr_path in adr_files:
        match = re.match(r"^(\d{4})-(.+)\.md$", adr_path.name)
        if not match:
            print(f"[FAIL] ADR 檔名格式不符 (應為 4 位數字-kebab-case.md): {adr_path.name}")
            all_ok = False
            continue

        num = int(match.group(1))
        if num != expected_num:
            print(f"[WARN] ADR 編號不連續: 預期 {expected_num:04d}，實際為 {num:04d} ({adr_path.name})")
        expected_num = num + 1

        # 2. 檢查是否登錄在 README.md 索引表
        rel_link = f"./{adr_path.name}"
        if rel_link not in readme_content and adr_path.name not in readme_content:
            print(f"[FAIL] ADR 未登載於 docs/adr/README.md 索引表: {adr_path.name}")
            all_ok = False

        # 3. 檢查 ADR 內容是否具備狀態聲明
        content = adr_path.read_text(encoding="utf-8")
        if "已採納" not in content and "提案中" not in content and "Accepted" not in content and "Proposed" not in content:
            print(f"[WARN] ADR 缺少明確狀態標註 (已採納/提案中): {adr_path.name}")

    if all_ok:
        print(f"[PASS] 所有 ADR ({len(adr_files)} 個) 均已完整且合法登載於 docs/adr/README.md 索引表")

    return all_ok


def main():
    print("=== [doc-sync] 文檔雙向同步一致性檢驗 ===")
    ok1 = check_basic_docs_exist()
    ok2 = check_adr_sync()
    ok3 = check_directory_docs(DOCS_SPECS_DIR, "需求與技術實作規格 (Specs)", DOCS_README)
    ok4 = check_directory_docs(DOCS_QA_DIR, "QA 實測驗收報告 (QA Reports)", DOCS_README)

    if ok1 and ok2 and ok3 and ok4:
        print("\n>>> [SUCCESS] 核心文檔、ADR、規格書與 QA 報告檢驗全數合格 (100% In Sync) <<<\n")
        sys.exit(0)
    else:
        print("\n>>> [ERROR] 文檔同步檢驗未通過，請對照檢核清單修復 <<<\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
