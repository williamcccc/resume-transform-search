#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_config.py
-----------------
讀取並驗證閉環專案設定 `.agents/project.toml`（Spec-0028）。

設計原則：缺檔或缺鍵一律拋出 ProjectConfigError，不提供隱含預設值，
避免移植到新專案時在不知情下沿用原專案的值。
"""

import tomllib
from pathlib import Path
from typing import Dict, Iterable, Optional

CONFIG_REL_PATH = Path(".agents") / "project.toml"

# 各區段必要鍵與型別；"str_list" 表示字串陣列。
SCHEMA: Dict[str, Dict[str, str]] = {
    "layers": {
        "enabled": "bool",
        "src": "str",
        "domain": "str",
        "application": "str",
        "infrastructure": "str",
        "interfaces": "str",
        "domain_interfaces": "str",
    },
    "config": {
        "module": "str",
        "env_example": "str",
    },
    "guardrails": {
        "url_schemes": "str_list",
        "api_key_patterns": "str_list",
        "prompt_indicators": "str_list",
        "eval_only_modules": "str_list",
        "required_gitignore": "str_list",
        "ignore_scan_dirs": "str_list",
        "url_exceptions": "exception_list",
    },
    "privacy": {
        "forbidden_hash_prefixes": "str_list",
        "safe_email_domains": "str_list",
        "safe_filename_stems": "str_list",
        "sensitive_dirs": "str_list",
        # 敏感目錄下視為隱私線索之副檔名（不含點；Spec-0038）
        "sensitive_extensions": "str_list",
        "personal_filename_keywords": "str_list",
        "locale_patterns": "str_list",
    },
    # 專案組成（Spec-0038）：移植時依此清單刪除業務技能
    "project": {
        "business_skills": "str_list",
    },
    "docs": {
        "quality_ac_enforced_from": "int",
        "security_ac_enforced_from": "int",
        "agents_max_lines": "int",
    },
    # 專案安全特徵（Spec-0030）：移植時只回答特徵，由框架對照適用標準
    "security": {
        "asvs_level": "int_range:1-3",
        "network_exposure": "enum:local|lan|internet",
        "web_interface": "bool",
        "api_service": "bool",
        "uses_llm": "bool",
        "handles_pii": "bool",
        "processes_untrusted_files": "bool",
        "multi_user": "bool",
        "not_applicable": "item_reason_list",
        # 有使用之技術條件章節（如 "V9"；Spec-0034）；技術章節須列於此或 not_applicable
        "tech_chapters_in_use": "str_list",
    },
    # Gate 2 安全掃描工具設定（Spec-0030）
    "security.tools": {
        "scan_paths": "str_list",
        "semgrep_configs": "str_list",
        "semgrep_block_severities": "str_list",
        "dependency_files": "str_list",
        "dependency_level": "enum:P0|P1",
        "baseline": "str",
        "tools_venv": "str",
        "diff_base": "str",
        "full_scan_max_age_days": "int_range:1-365",
    },
}


class ProjectConfigError(Exception):
    """project.toml 缺檔、語法錯誤、缺鍵或型別不符。"""


def _check_type(section: str, key: str, value, kind: str) -> None:
    where = f"[{section}].{key}"
    if kind == "bool":
        ok = isinstance(value, bool)
    elif kind == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "str":
        ok = isinstance(value, str) and value.strip() != ""
    elif kind == "str_list":
        ok = isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
    elif kind in ("exception_list", "item_reason_list"):
        fields = ("path", "reason") if kind == "exception_list" else ("item", "reason")
        if not isinstance(value, list):
            raise ProjectConfigError(f"{where} 須為陣列")
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ProjectConfigError(f"{where}[{index}] 須為表格（含 {' 與 '.join(fields)}）")
            for field in fields:
                field_value = item.get(field)
                if not isinstance(field_value, str) or not field_value.strip():
                    raise ProjectConfigError(f"{where}[{index}] 缺少必填欄位 {field}")
        return
    elif kind.startswith("enum:"):
        choices = kind[len("enum:"):].split("|")
        if not (isinstance(value, str) and value in choices):
            raise ProjectConfigError(f"{where} 須為 {' / '.join(choices)} 之一")
        return
    elif kind.startswith("int_range:"):
        low, high = (int(v) for v in kind[len("int_range:"):].split("-"))
        ok = isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
        if not ok:
            raise ProjectConfigError(f"{where} 須為 {low}～{high} 之整數")
        return
    else:  # pragma: no cover - SCHEMA 內部錯誤
        raise ProjectConfigError(f"未知的型別定義: {kind}")
    if not ok:
        raise ProjectConfigError(f"{where} 型別不符，應為 {kind}")


def load_project_config(root: Path, sections: Optional[Iterable[str]] = None) -> dict:
    """讀取 root 下的 project.toml，並驗證指定區段（預設全部）之必要鍵與型別。"""
    path = Path(root) / CONFIG_REL_PATH
    if not path.is_file():
        raise ProjectConfigError(f"找不到專案設定檔 {CONFIG_REL_PATH.as_posix()}，請依 .agents/PORTING.md 建立")
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as err:
        raise ProjectConfigError(f"{CONFIG_REL_PATH.as_posix()} 語法錯誤: {err}") from err

    for section in (sections if sections is not None else SCHEMA.keys()):
        if section not in SCHEMA:
            raise ProjectConfigError(f"未定義的設定區段: [{section}]")
        table = data
        for part in section.split("."):  # 支援巢狀區段，如 security.tools
            table = table.get(part) if isinstance(table, dict) else None
        if not isinstance(table, dict):
            raise ProjectConfigError(f"{CONFIG_REL_PATH.as_posix()} 缺少區段 [{section}]")
        for key, kind in SCHEMA[section].items():
            if key not in table:
                raise ProjectConfigError(f"{CONFIG_REL_PATH.as_posix()} 缺少必要鍵 [{section}].{key}")
            _check_type(section, key, table[key], kind)
    return data
