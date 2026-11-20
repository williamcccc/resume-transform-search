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
        "personal_filename_keywords": "str_list",
        "locale_patterns": "str_list",
    },
    "docs": {
        "quality_ac_enforced_from": "int",
        "agents_max_lines": "int",
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
    elif kind == "exception_list":
        if not isinstance(value, list):
            raise ProjectConfigError(f"{where} 須為陣列")
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ProjectConfigError(f"{where}[{index}] 須為表格（含 path 與 reason）")
            for field in ("path", "reason"):
                field_value = item.get(field)
                if not isinstance(field_value, str) or not field_value.strip():
                    raise ProjectConfigError(f"{where}[{index}] 缺少必填欄位 {field}")
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
        table = data.get(section)
        if not isinstance(table, dict):
            raise ProjectConfigError(f"{CONFIG_REL_PATH.as_posix()} 缺少區段 [{section}]")
        for key, kind in SCHEMA[section].items():
            if key not in table:
                raise ProjectConfigError(f"{CONFIG_REL_PATH.as_posix()} 缺少必要鍵 [{section}].{key}")
            _check_type(section, key, table[key], kind)
    return data
