#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_guardrails.py
-------------------
專案架構防線與 DDD 邊界自動化靜態檢查腳本。
使用 Python 內建 ast 模組進行 AST 語法樹解析，驗證整潔架構 (Clean Architecture)、DDD 邊界、
資源生命週期 (Windows File Lock 防禦)、例外處理與例外鏈完整度。

檢查項目：
1. [P0] Domain 層純潔性：src/domain/ 僅能依賴 Python 標準庫與同層模組，嚴禁引用外部套件 (如 redis, google.genai, docx, fitz 等) 或外層模組。
2. [P0] Application 層依賴反轉 (DIP)：src/application/ 僅能依賴 src/domain 與標準庫，嚴禁直接依賴 src/infrastructure 或 src/interfaces。
3. [P0] 資源生命週期安全：檢查 src/ 內是否有直接 open() 檔案卻未使用 with 語句 (避免 Windows 下 File Handle 鎖死)。
4. [P1] 異常吞噬檢查：檢查是否出現空的 `except: pass` 或 `except Exception: pass`。
5. [P1] 例外鏈完整度 (Exception Chaining)：檢查在 except 區塊中拋出新例外時是否缺少 `from err`。
6. [P0] 提示詞資產解耦 (Prompt-as-Code)：檢查 src/ 內是否有長篇提示詞寫死在代碼中，要求 100% 抽離至 prompts/*.md。
7. [P0] Git 版控衛生與隱私/路徑防線 (Git Hygiene & Privacy Markers)：檢查 .gitignore 邊界、.env.example 與 AppConfig 同步性、本機絕對路徑及已知隱私識別樣式。
"""

import ast
import hashlib
import io
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# 確保 Windows 終端輸出 UTF-8 編碼，避免 cp950 拋出 UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 依路徑動態解析出工作區根目錄
ROOT_DIR = Path(__file__).resolve().parents[4]
DOMAIN_DIR = ROOT_DIR / "src" / "domain"
APPLICATION_DIR = ROOT_DIR / "src" / "application"
SRC_DIR = ROOT_DIR / "src"

STDLIB_MODULES = set(sys.stdlib_module_names)


def check_domain_purity() -> List[str]:
    """檢查 src/domain/ 的所有模組，確認零外部套件依賴與零外層模組依賴。"""
    violations = []
    if not DOMAIN_DIR.exists():
        return violations

    for py_file in DOMAIN_DIR.glob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            violations.append(f"[Syntax Error] {py_file.name}: 無法解析語法樹 - {e}")
            continue

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", "?")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != "src":
                        violations.append(
                            f"[P0 違規 - Domain 引入外部第三方套件] {py_file.name}:{line_no} -> 'import {alias.name}'"
                        )
                    elif root_mod == "src":
                        if not alias.name.startswith("src.domain"):
                            violations.append(
                                f"[P0 違規 - Domain 逆向依賴外層模組] {py_file.name}:{line_no} -> 'import {alias.name}'"
                            )
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    # 相對引用，同在 domain 內視為合法
                    continue
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != "src":
                        violations.append(
                            f"[P0 違規 - Domain 引入外部第三方套件] {py_file.name}:{line_no} -> 'from {node.module} import ...'"
                        )
                    elif root_mod == "src":
                        if not node.module.startswith("src.domain"):
                            violations.append(
                                f"[P0 違規 - Domain 逆向依賴外層模組] {py_file.name}:{line_no} -> 'from {node.module} import ...'"
                            )

    return violations


def check_application_dip() -> List[str]:
    """檢查 src/application/，確認依賴反轉，嚴禁直接引用 infrastructure, interfaces 或外部第三方套件。"""
    violations = []
    if not APPLICATION_DIR.exists():
        return violations

    for py_file in APPLICATION_DIR.glob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            violations.append(f"[Syntax Error] {py_file.name}: 無法解析語法樹 - {e}")
            continue

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", "?")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != "src":
                        violations.append(
                            f"[P0 違規 - Application 引入外部第三方套件] {py_file.name}:{line_no} -> 'import {alias.name}' (應用層僅能依賴 Domain 與標準庫)"
                        )
                    elif "src.infrastructure" in alias.name or "src.interfaces" in alias.name:
                        violations.append(
                            f"[P0 違規 - Application 違反依賴反轉] {py_file.name}:{line_no} 直接引用外層模組: '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != "src":
                        violations.append(
                            f"[P0 違規 - Application 引入外部第三方套件] {py_file.name}:{line_no} -> 'from {node.module} import ...' (應用層僅能依賴 Domain 與標準庫)"
                        )
                    elif "src.infrastructure" in node.module or "src.interfaces" in node.module:
                        violations.append(
                            f"[P0 違規 - Application 違反依賴反轉] {py_file.name}:{line_no} 直接引用外層模組: 'from {node.module}'"
                        )

    return violations



def check_resource_lifecycle() -> List[str]:
    """檢查 src/ 內是否有直接呼叫 open() 卻未使用 with 語句管理生命週期（避免 Windows 檔案鎖死）。"""
    violations = []
    if not SRC_DIR.exists():
        return violations

    for py_file in SRC_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        # 建立父節點參照
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child._parent = parent

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                is_open_call = False
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    is_open_call = True
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "open":
                    is_open_call = True

                if is_open_call:
                    parent = getattr(node, "_parent", None)
                    # 合法的 context manager 呼叫，其 parent 應為 ast.withitem
                    if not isinstance(parent, ast.withitem):
                        line_no = getattr(node, "lineno", "?")
                        rel_path = py_file.relative_to(ROOT_DIR)
                        violations.append(
                            f"[P0 違規 - 資源未受 Context Manager 管理] {rel_path}:{line_no} -> 呼叫 open() 未使用 'with' 語句，在 Windows 易引發檔案鎖定 (WinError 32)"
                        )

    return violations


def check_exception_swallowing_and_chaining() -> Tuple[List[str], List[str]]:
    """檢查 src/ 內是否有空 except: pass 盲目吞掉例外，以及是否在拋出新例外時遺漏了 'from err'。"""
    swallow_warnings = []
    chaining_warnings = []
    if not SRC_DIR.exists():
        return swallow_warnings, chaining_warnings

    for py_file in SRC_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                line_no = getattr(node, "lineno", "?")
                rel_path = py_file.relative_to(ROOT_DIR)

                # 1. 檢查吞噬例外
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    type_str = ""
                    if node.type is None:
                        type_str = "裸的 except:"
                    elif isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
                        type_str = f"except {node.type.id}:"
                    
                    if type_str:
                        swallow_warnings.append(
                            f"[P1 警告 - 盲目吞噬例外] {rel_path}:{line_no} -> '{type_str} pass' 建議增加日誌記錄或精確捕獲"
                        )

                # 2. 檢查例外鏈 (Exception Chaining: raise ... from err)
                caught_var = node.name  # 例如 except Exception as e 中的 'e'
                if caught_var:
                    for child in ast.walk(node):
                        if isinstance(child, ast.Raise):
                            # 如果有拋出新例外且不是空的 raise
                            if child.exc and not (isinstance(child.exc, ast.Name) and child.exc.id == caught_var):
                                if child.cause is None:
                                    r_line = getattr(child, "lineno", line_no)
                                    chaining_warnings.append(
                                        f"[P1 警告 - 例外鏈斷裂] {rel_path}:{r_line} -> 重新拋出例外未帶 'from {caught_var}'，建議保留原始呼叫堆疊 (Traceback)"
                                    )

    return swallow_warnings, chaining_warnings


URL_PATTERN = re.compile(r"^(?:redis|postgres|postgresql|mongodb|amqp|https?)://[^\s\"']+", re.IGNORECASE)
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[a-zA-Z]:[\\/]|/(?:home|usr|var|etc|opt)[\\/])")
API_KEY_PATTERN = re.compile(r"(?:AQ\.[a-zA-Z0-9_-]{20,}|AIzaSy[a-zA-Z0-9_-]{33})")

PROMPT_INDICATORS = [
    "你是一個",
    "你是一位",
    "你扮演",
    "請遵守以下規則",
    "遵守以下規則",
    "<resume_content",
    "</resume_content>",
    "自我修復後的",
    "請對照原始資料",
    "你是一個專業的",
    "=== 原始文件資訊",
    "=== 待審核",
    "=== 原始提取文字",
]


def check_prompt_hardcoding() -> List[str]:
    """檢查 src/ 內是否有提示詞 (Prompt) 或模板硬編碼在代碼中，要求 100% 抽離至 prompts/*.md 資產目錄。"""
    p0_errors = []
    if not SRC_DIR.exists():
        return p0_errors

    for py_file in SRC_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(ROOT_DIR)

        # 排除 prompts 載入器本身
        if "prompts" in rel_path.parts:
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", "?")

            # 檢查字串常數
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip()
                matched_indicator = next((ind for ind in PROMPT_INDICATORS if ind in val), None)
                if matched_indicator and len(val) >= 20:
                    p0_errors.append(
                        f"[P0 違規 - 提示詞寫死 (Prompt Hardcoding)] {rel_path}:{line_no} -> 偵測到硬編碼提示詞 ({len(val)} 字元，包含 '{matched_indicator}')。所有提示詞必須抽離至 prompts/*.md 資產目錄並透過 load_prompt() 載入"
                    )

    return p0_errors


def check_hardcoded_configuration() -> Tuple[List[str], List[str]]:
    """檢查 src/ 內是否硬編碼金鑰、外部 URL 連線位址、本機絕對路徑或 Application 層寫死配額。"""
    p0_errors = []
    p1_warnings = []
    if not SRC_DIR.exists():
        return p0_errors, p1_warnings

    for py_file in SRC_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(ROOT_DIR)
        is_config_module = (rel_path == Path("src/infrastructure/config.py"))

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", "?")

            # 1. 檢查字串常數 (ast.Constant)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip()

                # 檢查 A: API Key 明文硬編碼 (P0 致命違規)
                if API_KEY_PATTERN.search(val):
                    p0_errors.append(
                        f"[P0 違規 - 原始碼寫死機密憑證] {rel_path}:{line_no} -> 偵測到硬編碼 API Key 格式字串，禁止將機密憑證納入 Git 版控"
                    )

                # 檢查 B: 外部網路連線硬編碼 (除 config.py 與特定 store 預設值外禁止寫死 URL)
                if not is_config_module and URL_PATTERN.match(val):
                    if rel_path != Path("src/infrastructure/stores/redis_vector_store.py"):
                        p0_errors.append(
                            f"[P0 違規 - 寫死外部連線 URL] {rel_path}:{line_no} -> '{val[:40]}...' 禁止硬編碼連線位址，必須透過 AppConfig 注入"
                        )

                # 檢查 C: 本機絕對路徑硬編碼 (P1 跨平台警告)
                if ABSOLUTE_PATH_PATTERN.match(val):
                    p1_warnings.append(
                        f"[P1 警告 - 寫死本機絕對路徑] {rel_path}:{line_no} -> '{val}' 建議改用 pathlib.Path 相對路徑或環境變數"
                    )

            # 2. 檢查 Application 層全域變數寫死配額常數
            if rel_path.parts[:2] == ("src", "application") and isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("MAX_") and target.id.isupper():
                        p1_warnings.append(
                            f"[P1 警告 - Application 層全域常數硬編碼] {rel_path}:{line_no} -> 模組定義了 '{target.id}'，核心業務配額應一律透過 Use Case 建構子屬性注入"
                        )

    return p0_errors, p1_warnings


FORBIDDEN_PII_HASH_PREFIXES = {
    "03e6e7b373fdf9b2",
    "fd33828acba22b0c",
    "7bc129af776b874e",
    "b9820ab4f19e7ac7",
    "6862896e289fdce0",
    "ab41d159b7aabb68",
}

REQUIRED_GITIGNORE_ENTRIES = [
    ".env",
    "data/",
    "resume/",
    "resumes/",
    "output/",
    "output_md/",
    "markdown_out/",
    "markdown_output/",
    "quarantine/",
    "scorecards/",
    "logs/",
    "dump.rdb",
    "appendonlydir/",
]

IGNORE_SCAN_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "data",
    "resume",
    "resumes",
    "output",
    "output_md",
    "markdown_out",
    "markdown_output",
    "quarantine",
    "scorecards",
    "logs",
    "scratch",
    ".vscode",
}


MASKED_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{1,3}["
    + re.escape("".join(chr(code) for code in (0x25CB, 0x25CF, 0xFF0A)))
    + r"][\u4e00-\u9fff]{1,3}"
)
PERSONAL_RESUME_FILENAME_PATTERN = re.compile(
    r"(?<![\w\u4e00-\u9fff])(?!(?:sample|example|demo|test|fake|mock|bad|large|corrupt|invalid|fixture|candidate|document|source|output|converted|file)[_-])"
    r"(?:[\u4e00-\u9fff]{2,4}|[A-Z][a-z]{1,30})[-_]"
    r"(?:CV|resume)(?:\.[A-Za-z0-9]{1,6})?(?![\w\u4e00-\u9fff])"
)
RESUME_DIRECTORY_FILENAME_PATTERN = re.compile(
    r"(?<![\w])(?:data[/\\])?(?:resume|resumes|markdown_out|markdown_output|output_md)[/\\]"
    r"(?:[^\s/\\`<>()\[\]\"']+[/\\])*([^\s/\\`<>()\[\]\"']+)\.(?:pdf|docx|doc|md)\b",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b")
SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "invalid", "localhost"}
TAIWAN_MOBILE_PATTERN = re.compile(r"(?<!\d)(?:\+?886[- .]?)?0?9(?:[- .]?\d){8}(?!\d)")
TAIWAN_LANDLINE_PATTERN = re.compile(r"(?<!\d)0[2-8](?:[- .]?\d){7,8}(?!\d)")
TAIWAN_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)", re.IGNORECASE)
CJK_SEQUENCE_PATTERN = re.compile(r"[\u4e00-\u9fff]{3,4}")


def find_privacy_markers(text: str) -> List[str]:
    """Return privacy marker categories without returning matched content."""
    markers = set()

    if MASKED_CJK_PATTERN.search(text):
        markers.add("masked_cjk_identifier")
    safe_filename_stems = {
        "sample", "example", "demo", "test", "fake", "mock", "bad", "large",
        "corrupt", "invalid", "fixture", "candidate", "document", "source", "output",
        "converted", "file", "input", "resume", "sample_resume", "candidate_one",
    }
    for match in PERSONAL_RESUME_FILENAME_PATTERN.finditer(text):
        token = match.group(0)
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        is_quoted = before in {"`", "'", '"'} or after in {"`", "'", '"'}
        has_extension = bool(re.search(r"\.[A-Za-z0-9]{1,6}$", token))
        stem = re.split(r"[-_]", token, maxsplit=1)[0].lower()
        if (is_quoted or has_extension) and stem not in safe_filename_stems:
            markers.add("personal_resume_filename")
    for match in RESUME_DIRECTORY_FILENAME_PATTERN.finditer(text):
        stem = Path(match.group(1)).stem.lower()
        if stem not in safe_filename_stems:
            markers.add("personal_resume_filename")
    for match in EMAIL_PATTERN.finditer(text):
        domain = match.group(1).lower()
        if domain not in SAFE_EMAIL_DOMAINS and not any(
            domain.endswith("." + safe_domain) for safe_domain in SAFE_EMAIL_DOMAINS
        ):
            markers.add("email_address")
    if TAIWAN_MOBILE_PATTERN.search(text) or TAIWAN_LANDLINE_PATTERN.search(text):
        markers.add("phone_number")
    if TAIWAN_ID_PATTERN.search(text):
        markers.add("taiwan_id_number")

    for seq in set(CJK_SEQUENCE_PATTERN.findall(text)):
        for length in (3, 4):
            if len(seq) < length:
                continue
            for index in range(len(seq) - length + 1):
                fingerprint = hashlib.sha256(seq[index : index + length].encode("utf-8")).hexdigest()[:16]
                if fingerprint in FORBIDDEN_PII_HASH_PREFIXES:
                    markers.add("protected_identity_fingerprint")
                    break

    return sorted(markers)


def safe_path_for_report(relative_path: str, path_markers: List[str]) -> str:
    """Hide a repository path when the path itself contains a privacy marker."""
    return "[redacted-path]" if path_markers else relative_path


def check_git_hygiene_and_pii_guardrails() -> List[str]:
    """檢查版控邊界、環境範本、工作區路徑與已知隱私識別樣式。"""
    p0_errors = []

    # 1. 檢查 .gitignore 必要項目
    gitignore_path = ROOT_DIR / ".gitignore"
    if not gitignore_path.exists():
        p0_errors.append("[P0 違規 - 缺少 .gitignore] 專案根目錄缺少 .gitignore 版控保護檔")
    else:
        lines = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for req in REQUIRED_GITIGNORE_ENTRIES:
            if req not in lines:
                p0_errors.append(f"[P0 違規 - .gitignore 漏列敏感路徑] .gitignore 缺少必備保護規則: '{req}'")

    # 2. 檢查 .env.example 與 AppConfig 100% 同步且無真實金鑰
    config_path = ROOT_DIR / "src" / "infrastructure" / "config.py"
    env_example_path = ROOT_DIR / ".env.example"
    if config_path.exists() and env_example_path.exists():
        cfg_text = config_path.read_text(encoding="utf-8")
        ex_text = env_example_path.read_text(encoding="utf-8")
        cfg_keys = set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z0-9_]+)["\']', cfg_text))
        ex_keys = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", ex_text, re.MULTILINE))
        missing_keys = sorted(cfg_keys - ex_keys)
        if missing_keys:
            p0_errors.append(
                f"[P0 違規 - .env.example 未同步環境變數] AppConfig 中的變數未列於 .env.example: {missing_keys}"
            )
        if API_KEY_PATTERN.search(ex_text):
            p0_errors.append("[P0 違規 - .env.example 含真實金鑰] .env.example 嚴禁包含真實 API Key")

    # 3. 檢查全專案 Git 候選檔案是否殘留本機路徑、金鑰或已知隱私識別樣式
    ws_pat = re.compile(r"[cC]:[/\\]+" + "Python" + "Workspace")
    binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".doc"}

    for file_path in ROOT_DIR.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = set(file_path.relative_to(ROOT_DIR).parts)
        if rel_parts & IGNORE_SCAN_DIRS or file_path.name == ".env":
            continue
        rel_str = str(file_path.relative_to(ROOT_DIR))
        path_markers = find_privacy_markers(rel_str)
        markers = set(path_markers)
        reported_path = safe_path_for_report(rel_str, path_markers)
        if file_path.suffix.lower() not in binary_exts:
            try:
                text = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            markers.update(find_privacy_markers(text))
        else:
            text = ""

        if ws_pat.search(text):
            p0_errors.append(f"[P0 違規 - 殘留本機工作區絕對路徑] {reported_path} 包含本機工作區絕對路徑硬編碼")
        if API_KEY_PATTERN.search(text):
            p0_errors.append(f"[P0 違規 - 版控檔案洩漏機密金鑰] {reported_path} 包含真實 API Key 格式字串")
        for marker in sorted(markers):
            p0_errors.append(f"[P0 違規 - 隱私線索 {marker}] {reported_path}")

    return p0_errors


def main() -> int:
    print("=" * 70)
    print("🔍 啟動 Clean Architecture & DDD 防線靜態代碼稽核 (Code Review)")
    print(f"工作區根目錄: {ROOT_DIR}")
    print("=" * 70)

    all_p0_errors = []
    all_p1_warnings = []

    # 1. Domain 純潔性檢查
    domain_errs = check_domain_purity()
    all_p0_errors.extend(domain_errs)
    if not domain_errs:
        print("✅ [Pass] Domain 層純潔性驗證：零外部套件、零外層依賴。")
    else:
        for err in domain_errs:
            print(f"❌ {err}")

    # 2. Application 依賴反轉檢查
    app_errs = check_application_dip()
    all_p0_errors.extend(app_errs)
    if not app_errs:
        print("✅ [Pass] Application 層依賴反轉驗證：完全透過 Domain Interface 協調整合。")
    else:
        for err in app_errs:
            print(f"❌ {err}")

    # 3. 資源釋放生命週期檢查 (Context Manager)
    resource_errs = check_resource_lifecycle()
    all_p0_errors.extend(resource_errs)
    if not resource_errs:
        print("✅ [Pass] 資源管理生命週期驗證：檔案 I/O 均受到 Context Manager (with) 嚴格保護。")
    else:
        for err in resource_errs:
            print(f"❌ {err}")

    # 4. 異常吞噬與例外鏈完整度檢查
    swallow_warnings, chaining_warnings = check_exception_swallowing_and_chaining()
    all_p1_warnings.extend(swallow_warnings)
    all_p1_warnings.extend(chaining_warnings)
    
    if not swallow_warnings:
        print("✅ [Pass] 例外處理防護檢查：無盲目吞噬 Exception 行為。")
    else:
        for w in swallow_warnings:
            print(f"⚠️  {w}")

    if not chaining_warnings:
        print("✅ [Pass] 例外鏈完整度檢查：重新拋出例外皆完整保留 'from err' 堆疊。")
    else:
        for w in chaining_warnings:
            print(f"⚠️  {w}")

    # 5. Twelve-Factor 配置與零硬編碼檢查
    hardcode_p0, hardcode_p1 = check_hardcoded_configuration()
    all_p0_errors.extend(hardcode_p0)
    all_p1_warnings.extend(hardcode_p1)

    if not hardcode_p0:
        print("✅ [Pass] Twelve-Factor 配置與零硬編碼驗證：零寫死金鑰、零未受控 URL。")
    else:
        for err in hardcode_p0:
            print(f"❌ {err}")

    if hardcode_p1:
        for w in hardcode_p1:
            print(f"⚠️  {w}")

    # 6. Prompt Engineering 提示詞資產解耦檢查
    prompt_p0 = check_prompt_hardcoding()
    all_p0_errors.extend(prompt_p0)

    if not prompt_p0:
        print("✅ [Pass] Prompt 提示詞治理驗證：零硬編碼提示詞，100% 透過 prompts/*.md 資產管理。")
    else:
        for err in prompt_p0:
            print(f"❌ {err}")

    # 7. Git 版控衛生、個資清零與跨平台路徑防線檢查
    hygiene_p0 = check_git_hygiene_and_pii_guardrails()
    all_p0_errors.extend(hygiene_p0)

    if not hygiene_p0:
        print("✅ [Pass] Git 版控衛生與隱私防線驗證：已知隱私規則零命中、零工作區路徑，.gitignore 與 .env.example 對齊。")
    else:
        for err in hygiene_p0:
            print(f"❌ {err}")

    print("=" * 70)
    if all_p0_errors:
        print(f"🚨 審查失敗 (FAILED)：發現 {len(all_p0_errors)} 項 P0 級架構違規！請務必修正後再行交付。")
        return 1
    elif all_p1_warnings:
        print(f"⚠️  審查通過但有警告 (PASSED with warnings)：發現 {len(all_p1_warnings)} 項建議優化項目。")
        return 0
    else:
        print("🎉 審查完全合格 (100% PASSED)：架構分層、邊界防護與例外處理完全符合規格！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
