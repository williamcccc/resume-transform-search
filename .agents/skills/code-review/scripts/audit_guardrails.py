#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_guardrails.py
-------------------
專案架構防線與 DDD 邊界自動化靜態檢查腳本。
使用 Python 內建 ast 模組進行 AST 語法樹解析，驗證整潔架構 (Clean Architecture)、DDD 邊界、
資源生命週期 (Windows File Lock 防禦)、例外處理與例外鏈完整度。

所有專案專屬的路徑、清單與樣式皆讀自 `.agents/project.toml`（Spec-0028）；
以下「原始碼根目錄」「Domain 層」等指稱，對應該檔 [layers] 區段之設定值。

檢查項目：
1. [P0] Domain 層純潔性：Domain 層僅能依賴 Python 標準庫與同層模組，嚴禁引用外部套件或外層模組（[layers].enabled = false 時略過）。
2. [P0] Application 層依賴反轉 (DIP)：Application 層僅能依賴 Domain 層與標準庫，嚴禁直接依賴 Infrastructure 或 Interfaces 層（[layers].enabled = false 時略過）。
3. [P0] 資源生命週期安全：檢查原始碼內是否有直接 open() 檔案卻未使用 with 語句 (避免 Windows 下 File Handle 鎖死)。
4. [P1] 異常吞噬檢查：檢查是否出現空的 `except: pass` 或 `except Exception: pass`。
5. [P1] 例外鏈完整度 (Exception Chaining)：檢查在 except 區塊中拋出新例外時是否缺少 `from err`。
6. [P0] 提示詞資產解耦 (Prompt-as-Code)：檢查原始碼內是否有長篇提示詞寫死在代碼中，要求 100% 抽離至 prompts/*.md。
7. [P0] Git 版控衛生與隱私/路徑防線 (Git Hygiene & Privacy Markers)：檢查 .gitignore 邊界、環境變數範本與設定模組同步性、本機絕對路徑及已知隱私識別樣式。
8. [P0] 評測專用依賴隔離：原始碼任何層級嚴禁 import [guardrails].eval_only_modules 所列之評測套件，該類套件僅限 tests/eval/ 使用。

結束碼：0 通過；1 有 P0 違規；2 專案設定檔缺漏或錯誤。
"""

import ast
import hashlib
import io
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 確保 Windows 終端輸出 UTF-8 編碼，避免 cp950 拋出 UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 依路徑動態解析出工作區根目錄
ROOT_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(ROOT_DIR / ".agents" / "lib"))
from project_config import ProjectConfigError, load_project_config  # noqa: E402

try:
    CONFIG = load_project_config(ROOT_DIR, ("layers", "config", "guardrails", "privacy"))
except ProjectConfigError as _config_err:
    print(f"❌ [設定錯誤] {_config_err}", file=sys.stderr)
    sys.exit(2)

_LAYERS = CONFIG["layers"]
_GUARDRAILS = CONFIG["guardrails"]
_PRIVACY = CONFIG["privacy"]


def _module_name(rel_dir: str) -> str:
    """將專案相對目錄轉為 Python 模組路徑，如 'src/domain' → 'src.domain'。"""
    return Path(rel_dir).as_posix().strip("/").replace("/", ".")


LAYERS_ENABLED = _LAYERS["enabled"]
SRC_DIR = ROOT_DIR / _LAYERS["src"]
DOMAIN_DIR = ROOT_DIR / _LAYERS["domain"]
APPLICATION_DIR = ROOT_DIR / _LAYERS["application"]
SRC_PACKAGE = _module_name(_LAYERS["src"]).split(".")[0]
DOMAIN_PACKAGE = _module_name(_LAYERS["domain"])
INFRASTRUCTURE_PACKAGE = _module_name(_LAYERS["infrastructure"])
INTERFACES_PACKAGE = _module_name(_LAYERS["interfaces"])
APPLICATION_PARTS = Path(_LAYERS["application"]).parts
CONFIG_MODULE_PATH = Path(CONFIG["config"]["module"])
ENV_EXAMPLE_PATH = Path(CONFIG["config"]["env_example"])
URL_EXCEPTION_PATHS = {Path(item["path"]) for item in _GUARDRAILS["url_exceptions"]}

STDLIB_MODULES = set(sys.stdlib_module_names)


def _is_outer_layer(module: str) -> bool:
    """模組是否屬於 Infrastructure 或 Interfaces 層。"""
    return any(
        module == package or module.startswith(package + ".")
        for package in (INFRASTRUCTURE_PACKAGE, INTERFACES_PACKAGE)
    )


def _layer_python_files(layer_dir: Path) -> List[Path]:
    """分層目錄下所有 .py 檔（含任意深度子資料夾，排除 __pycache__；Bug-0031）。"""
    return sorted(p for p in layer_dir.rglob("*.py") if "__pycache__" not in p.parts)


def check_domain_purity() -> List[str]:
    """檢查 Domain 層所有模組，確認零外部套件依賴與零外層模組依賴。"""
    violations = []
    if not LAYERS_ENABLED or not DOMAIN_DIR.exists():
        return violations

    for py_file in _layer_python_files(DOMAIN_DIR):
        rel_name = py_file.relative_to(ROOT_DIR).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            violations.append(f"[Syntax Error] {rel_name}: 無法解析語法樹 - {e}")
            continue

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", "?")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != SRC_PACKAGE:
                        violations.append(
                            f"[P0 違規 - Domain 引入外部第三方套件] {rel_name}:{line_no} -> 'import {alias.name}'"
                        )
                    elif root_mod == SRC_PACKAGE:
                        if not alias.name.startswith(DOMAIN_PACKAGE):
                            violations.append(
                                f"[P0 違規 - Domain 逆向依賴外層模組] {rel_name}:{line_no} -> 'import {alias.name}'"
                            )
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    # 相對引用，同在 domain 內視為合法
                    continue
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != SRC_PACKAGE:
                        violations.append(
                            f"[P0 違規 - Domain 引入外部第三方套件] {rel_name}:{line_no} -> 'from {node.module} import ...'"
                        )
                    elif root_mod == SRC_PACKAGE:
                        if not node.module.startswith(DOMAIN_PACKAGE):
                            violations.append(
                                f"[P0 違規 - Domain 逆向依賴外層模組] {rel_name}:{line_no} -> 'from {node.module} import ...'"
                            )

    return violations


def check_application_dip() -> List[str]:
    """檢查 Application 層，確認依賴反轉，嚴禁直接引用 Infrastructure、Interfaces 層或外部第三方套件。"""
    violations = []
    if not LAYERS_ENABLED or not APPLICATION_DIR.exists():
        return violations

    for py_file in _layer_python_files(APPLICATION_DIR):
        rel_name = py_file.relative_to(ROOT_DIR).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            violations.append(f"[Syntax Error] {rel_name}: 無法解析語法樹 - {e}")
            continue

        for node in ast.walk(tree):
            line_no = getattr(node, "lineno", "?")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != SRC_PACKAGE:
                        violations.append(
                            f"[P0 違規 - Application 引入外部第三方套件] {rel_name}:{line_no} -> 'import {alias.name}' (應用層僅能依賴 Domain 與標準庫)"
                        )
                    elif _is_outer_layer(alias.name):
                        violations.append(
                            f"[P0 違規 - Application 違反依賴反轉] {rel_name}:{line_no} 直接引用外層模組: '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod not in STDLIB_MODULES and root_mod != SRC_PACKAGE:
                        violations.append(
                            f"[P0 違規 - Application 引入外部第三方套件] {rel_name}:{line_no} -> 'from {node.module} import ...' (應用層僅能依賴 Domain 與標準庫)"
                        )
                    elif _is_outer_layer(node.module):
                        violations.append(
                            f"[P0 違規 - Application 違反依賴反轉] {rel_name}:{line_no} 直接引用外層模組: 'from {node.module}'"
                        )

    return violations



def check_resource_lifecycle() -> List[str]:
    """檢查原始碼內是否有直接呼叫 open() 卻未使用 with 語句管理生命週期（避免 Windows 檔案鎖死）。"""
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
    """檢查原始碼內是否有空 except: pass 盲目吞掉例外，以及是否在拋出新例外時遺漏了 'from err'。"""
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


def _alternation(items: List[str]) -> str:
    return "|".join(re.escape(item) for item in items)


class _NeverMatch:
    """設定清單為空時的替代樣式：任何輸入皆不命中（避免空的 (?:) 誤命中所有字串）。"""

    def search(self, _text):
        return None

    def match(self, _text):
        return None

    def finditer(self, _text):
        return iter(())


def _compile_or_never(pattern_body: str, items: List[str], flags: int = 0):
    return re.compile(pattern_body, flags) if items else _NeverMatch()


URL_PATTERN = _compile_or_never(
    r"^(?:" + _alternation(_GUARDRAILS["url_schemes"]) + r")://[^\s\"']+",
    _GUARDRAILS["url_schemes"],
    re.IGNORECASE,
)
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[a-zA-Z]:[\\/]|/(?:home|usr|var|etc|opt)[\\/])")
try:
    API_KEY_PATTERN = _compile_or_never(
        "(?:" + "|".join(f"(?:{p})" for p in _GUARDRAILS["api_key_patterns"]) + ")",
        _GUARDRAILS["api_key_patterns"],
    )
except re.error as _pattern_err:
    print(f"❌ [設定錯誤] [guardrails].api_key_patterns 正規式無效: {_pattern_err}", file=sys.stderr)
    sys.exit(2)

PROMPT_INDICATORS = list(_GUARDRAILS["prompt_indicators"])


def check_prompt_hardcoding() -> List[str]:
    """檢查原始碼內是否有提示詞 (Prompt) 或模板硬編碼在代碼中，要求 100% 抽離至 prompts/*.md 資產目錄。"""
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
    """檢查原始碼內是否硬編碼金鑰、外部 URL 連線位址、本機絕對路徑或 Application 層寫死配額。"""
    p0_errors = []
    p1_warnings = []
    if not SRC_DIR.exists():
        return p0_errors, p1_warnings

    for py_file in SRC_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(ROOT_DIR)
        is_config_module = (rel_path == CONFIG_MODULE_PATH)

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

                # 檢查 B: 外部網路連線硬編碼 (除設定模組與 [guardrails].url_exceptions 外禁止寫死 URL)
                if not is_config_module and URL_PATTERN.match(val):
                    if rel_path not in URL_EXCEPTION_PATHS:
                        p0_errors.append(
                            f"[P0 違規 - 寫死外部連線 URL] {rel_path}:{line_no} -> '{val[:40]}...' 禁止硬編碼連線位址，必須透過 AppConfig 注入"
                        )

                # 檢查 C: 本機絕對路徑硬編碼 (P1 跨平台警告)
                if ABSOLUTE_PATH_PATTERN.match(val):
                    p1_warnings.append(
                        f"[P1 警告 - 寫死本機絕對路徑] {rel_path}:{line_no} -> '{val}' 建議改用 pathlib.Path 相對路徑或環境變數"
                    )

            # 2. 檢查 Application 層全域變數寫死配額常數
            if (
                LAYERS_ENABLED
                and rel_path.parts[: len(APPLICATION_PARTS)] == APPLICATION_PARTS
                and isinstance(node, ast.Assign)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith("MAX_") and target.id.isupper():
                        p1_warnings.append(
                            f"[P1 警告 - Application 層全域常數硬編碼] {rel_path}:{line_no} -> 模組定義了 '{target.id}'，核心業務配額應一律透過 Use Case 建構子屬性注入"
                        )

    return p0_errors, p1_warnings


FORBIDDEN_PII_HASH_PREFIXES = set(_PRIVACY["forbidden_hash_prefixes"])
REQUIRED_GITIGNORE_ENTRIES = list(_GUARDRAILS["required_gitignore"])
IGNORE_SCAN_DIRS = set(_GUARDRAILS["ignore_scan_dirs"])
SAFE_FILENAME_STEMS = {stem.lower() for stem in _PRIVACY["safe_filename_stems"]}
SAFE_EMAIL_DOMAINS = {domain.lower() for domain in _PRIVACY["safe_email_domains"]}


MASKED_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{1,3}["
    + re.escape("".join(chr(code) for code in (0x25CB, 0x25CF, 0xFF0A)))
    + r"][\u4e00-\u9fff]{1,3}"
)
_SAFE_STEM_LOOKAHEAD = (
    r"(?!(?:" + _alternation(sorted(SAFE_FILENAME_STEMS)) + r")[_-])" if SAFE_FILENAME_STEMS else ""
)
PERSONAL_FILENAME_PATTERN = _compile_or_never(
    r"(?<![\w\u4e00-\u9fff])" + _SAFE_STEM_LOOKAHEAD
    + r"(?:[\u4e00-\u9fff]{2,4}|[A-Z][a-z]{1,30})[-_]"
    + r"(?:" + _alternation(_PRIVACY["personal_filename_keywords"]) + r")"
    + r"(?:\.[A-Za-z0-9]{1,6})?(?![\w\u4e00-\u9fff])",
    _PRIVACY["personal_filename_keywords"],
)
def sensitive_directory_filename_pattern(dirs, extensions):
    """敏感目錄下引用指定副檔名之實際檔名；任一清單為空時永不命中（Spec-0038）。"""
    if not dirs or not extensions:
        return _NeverMatch()
    return re.compile(
        r"(?<![\w])(?:" + _alternation(dirs) + r")[/\\]"
        r"(?:[^\s/\\`<>()\[\]\"']+[/\\])*([^\s/\\`<>()\[\]\"']+)\.(?:" + _alternation(extensions) + r")\b",
        re.IGNORECASE,
    )


SENSITIVE_DIRECTORY_FILENAME_PATTERN = sensitive_directory_filename_pattern(
    _PRIVACY["sensitive_dirs"], _PRIVACY["sensitive_extensions"]
)
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b")
CJK_SEQUENCE_PATTERN = re.compile(r"[\u4e00-\u9fff]{3,4}")

# \u5167\u5efa\u5730\u5340\u6a23\u5f0f\u7d44\uff1a\u540d\u7a31 \u2192 (\u6a23\u5f0f, \u96b1\u79c1\u7dda\u7d22\u985e\u5225)\uff1b\u7531 [privacy].locale_patterns \u9078\u7528
LOCALE_PATTERN_SETS = {
    "tw_mobile": (re.compile(r"(?<!\d)(?:\+?886[- .]?)?0?9(?:[- .]?\d){8}(?!\d)"), "phone_number"),
    "tw_landline": (re.compile(r"(?<!\d)0[2-8](?:[- .]?\d){7,8}(?!\d)"), "phone_number"),
    "tw_id": (re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?!\d)", re.IGNORECASE), "taiwan_id_number"),
}
_unknown_locales = sorted(set(_PRIVACY["locale_patterns"]) - LOCALE_PATTERN_SETS.keys())
if _unknown_locales:
    print(
        f"\u274c [\u8a2d\u5b9a\u932f\u8aa4] [privacy].locale_patterns \u542b\u672a\u5b9a\u7fa9\u7684\u6a23\u5f0f\u7d44: {_unknown_locales}\uff1b"
        f"\u53ef\u7528: {sorted(LOCALE_PATTERN_SETS)}",
        file=sys.stderr,
    )
    sys.exit(2)
ACTIVE_LOCALE_PATTERNS = [LOCALE_PATTERN_SETS[name] for name in _PRIVACY["locale_patterns"]]


def find_privacy_markers(text: str) -> List[str]:
    """Return privacy marker categories without returning matched content."""
    markers = set()

    if MASKED_CJK_PATTERN.search(text):
        markers.add("masked_cjk_identifier")
    safe_filename_stems = SAFE_FILENAME_STEMS
    for match in PERSONAL_FILENAME_PATTERN.finditer(text):
        token = match.group(0)
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        is_quoted = before in {"`", "'", '"'} or after in {"`", "'", '"'}
        has_extension = bool(re.search(r"\.[A-Za-z0-9]{1,6}$", token))
        stem = re.split(r"[-_]", token, maxsplit=1)[0].lower()
        if (is_quoted or has_extension) and stem not in safe_filename_stems:
            markers.add("personal_filename")
    for match in SENSITIVE_DIRECTORY_FILENAME_PATTERN.finditer(text):
        stem = Path(match.group(1)).stem.lower()
        if stem not in safe_filename_stems:
            markers.add("personal_filename")
    for match in EMAIL_PATTERN.finditer(text):
        domain = match.group(1).lower()
        if domain not in SAFE_EMAIL_DOMAINS and not any(
            domain.endswith("." + safe_domain) for safe_domain in SAFE_EMAIL_DOMAINS
        ):
            markers.add("email_address")
    for pattern, marker in ACTIVE_LOCALE_PATTERNS:
        if pattern.search(text):
            markers.add(marker)

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


def workspace_path_pattern(root: Path) -> "re.Pattern[str]":
    """由工作區實際根目錄組出比對樣式：磁碟代號不分大小寫，路徑分隔符 / 與 \\ 皆可。"""
    anchor = root.anchor.rstrip("/\\")
    names = [re.escape(part) for part in root.parts[1:]]
    prefix = ""
    if anchor:
        prefix = "".join(
            f"[{ch.lower()}{ch.upper()}]" if ch.isalpha() else re.escape(ch) for ch in anchor
        )
    if not names:  # 工作區位於磁碟根目錄時無可辨識之資料夾名稱，略過此檢查
        return _NeverMatch()
    body = r"[/\\]+".join(names)
    return re.compile(prefix + r"[/\\]+" + body)


def parse_env_example_keys(text: str) -> set:
    """`.env.example` 中列出之變數名稱（含註解掉的 `# NAME=` 範例）。"""
    return set(re.findall(r"^#?\s*([A-Z0-9_]+)=", text, re.MULTILINE))


def _env_scan_files(config_path: Path) -> List[Path]:
    """環境變數偵測範圍：layers.src 下所有 .py，另含位於 src 之外的設定模組（Bug-0032）。"""
    files = sorted(p for p in SRC_DIR.rglob("*.py") if "__pycache__" not in p.parts) if SRC_DIR.exists() else []
    if config_path.is_file() and config_path not in files:
        files.append(config_path)
    return files


def collect_env_var_reads(files) -> Dict[str, List[str]]:
    """以 AST 收集以字串常值讀取之環境變數：os.environ.get / os.getenv / os.environ[...]，
    含 `from os import environ, getenv` 寫法。動態取名（變數、迴圈）無法靜態判定，不收集。
    回傳 {變數名: [「相對路徑:行號」...]}（Bug-0032）。"""
    reads: Dict[str, List[str]] = {}

    def is_environ(node) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "environ"
                and isinstance(node.value, ast.Name) and node.value.id == "os") or (
            isinstance(node, ast.Name) and node.id in environ_names)

    def literal(node):
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        environ_names, getenv_names = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "os":
                for alias in node.names:
                    if alias.name == "environ":
                        environ_names.add(alias.asname or alias.name)
                    elif alias.name == "getenv":
                        getenv_names.add(alias.asname or alias.name)
        try:
            rel = path.relative_to(ROOT_DIR).as_posix()
        except ValueError:
            rel = path.as_posix()
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Call) and node.args:
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "get" and is_environ(func.value):
                    name = literal(node.args[0])
                elif isinstance(func, ast.Attribute) and func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os":
                    name = literal(node.args[0])
                elif isinstance(func, ast.Name) and func.id in getenv_names:
                    name = literal(node.args[0])
            elif isinstance(node, ast.Subscript) and is_environ(node.value):
                name = literal(node.slice)
            if name:
                reads.setdefault(name, []).append(f"{rel}:{getattr(node, 'lineno', '?')}")
    return reads


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
    config_path = ROOT_DIR / CONFIG_MODULE_PATH
    env_example_path = ROOT_DIR / ENV_EXAMPLE_PATH
    if config_path.exists() and env_example_path.exists():
        ex_text = env_example_path.read_text(encoding="utf-8")
        env_reads = collect_env_var_reads(_env_scan_files(config_path))
        ex_keys = parse_env_example_keys(ex_text)
        missing = sorted(name for name in env_reads if name not in ex_keys)
        if missing:
            detail = "、".join(f"{name}（{env_reads[name][0]}）" for name in missing)
            p0_errors.append(
                f"[P0 違規 - .env.example 未同步環境變數] 原始碼讀取之環境變數未列於 .env.example: {detail}"
            )
        if API_KEY_PATTERN.search(ex_text):
            p0_errors.append("[P0 違規 - .env.example 含真實金鑰] .env.example 嚴禁包含真實 API Key")

    # 3. 檢查全專案 Git 候選檔案是否殘留本機路徑、金鑰或已知隱私識別樣式
    ws_pat = workspace_path_pattern(ROOT_DIR)
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


# 不進生產環境的評測專用套件（僅限 tests/eval/ 使用），見 [guardrails].eval_only_modules
EVAL_ONLY_MODULES = frozenset(_GUARDRAILS["eval_only_modules"])


def check_eval_only_imports(src_dir: Path = SRC_DIR) -> List[str]:
    """檢查原始碼全部模組（遞迴），確認未引用任何評測專用套件。"""
    violations = []
    if not src_dir.exists():
        return violations

    for py_file in sorted(src_dir.rglob("*.py")):
        rel = py_file.relative_to(src_dir.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as e:
            violations.append(f"[Syntax Error] {rel}: 無法解析語法樹 - {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for name in modules:
                if name.split(".")[0] in EVAL_ONLY_MODULES:
                    violations.append(
                        f"[P0 違規 - src 引入評測專用套件] {rel}:{node.lineno} -> '{name}' (僅限 tests/eval/ 使用)"
                    )

    return violations


def check_configured_paths() -> List[str]:
    """設定指向的檔案與目錄必須存在；不存在時回報 P0，避免後續檢查靜默跳過（Bug-0033）。"""
    errors = []
    expected = [
        ("layers.src", SRC_DIR, "dir"),
        ("config.module", ROOT_DIR / CONFIG_MODULE_PATH, "file"),
        ("config.env_example", ROOT_DIR / ENV_EXAMPLE_PATH, "file"),
    ]
    if LAYERS_ENABLED:
        expected += [("layers.domain", DOMAIN_DIR, "dir"), ("layers.application", APPLICATION_DIR, "dir")]
    for key, path, kind in expected:
        exists = path.is_dir() if kind == "dir" else path.is_file()
        if not exists:
            rel = path.relative_to(ROOT_DIR).as_posix() if path.is_relative_to(ROOT_DIR) else path.as_posix()
            label = "目錄" if kind == "dir" else "檔案"
            errors.append(
                f"[P0 違規 - 設定路徑不存在] project.toml 的 {key} 指向之{label}不存在: {rel}（相關檢查無法執行）"
            )
    return errors


def main() -> int:
    print("=" * 70)
    print("🔍 啟動 Clean Architecture & DDD 防線靜態代碼稽核 (Code Review)")
    print(f"工作區根目錄: {ROOT_DIR}")
    print("=" * 70)

    all_p0_errors = []
    all_p1_warnings = []

    # 0. 設定路徑存在性（Bug-0033：缺檔或缺目錄不得讓其他檢查靜默跳過）
    path_errs = check_configured_paths()
    all_p0_errors.extend(path_errs)
    if not path_errs:
        print("✅ [Pass] 設定路徑驗證：layers 與 config 指向之目錄、檔案皆存在。")
    else:
        for err in path_errs:
            print(f"❌ {err}")

    if LAYERS_ENABLED:
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
    else:
        print("⏭️  [Skip] DDD 分層檢查已停用（project.toml [layers].enabled = false）。")

    # 2b. 評測專用依賴隔離 (原始碼嚴禁 import 評測專用套件)
    eval_only_errs = check_eval_only_imports()
    all_p0_errors.extend(eval_only_errs)
    if not eval_only_errs:
        modules = "、".join(sorted(EVAL_ONLY_MODULES)) or "無"
        print(f"✅ [Pass] 評測專用依賴隔離驗證：原始碼零評測套件引用（{modules} 僅限 tests/eval/）。")
    else:
        for err in eval_only_errs:
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
