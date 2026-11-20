#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
security_scan.py
----------------
Gate 2 通用安全掃描閘門（Spec-0030）。依 `.agents/project.toml` 的 `[security.tools]` 執行：

1. Semgrep 靜態掃描（規則集由 semgrep_configs 指定）。
2. pip-audit 依賴漏洞掃描（需求檔由 dependency_files 指定）。

判定：
* 發現以指紋比對基準檔（baseline）；基準檔內且未到期者不阻斷。
* 新增或基準已到期之發現：Semgrep 嚴重度屬 semgrep_block_severities 者為 P0，其餘 P1；
  依賴漏洞依 dependency_level 判定。
* 工具無法連網（規則集下載、漏洞資料庫查詢）時印 WARN 並記為「未執行」，不阻斷。
* 工具未安裝、或非網路因素之執行錯誤時 FAIL。

觸發方式（Spec-0030 決議 10）：
* 差異掃描（預設）：Semgrep 只掃相對 diff_base 有變更且位於 scan_paths 內的檔案；
  pip-audit 只在 dependency_files 有變更時執行，且只掃變更的需求檔。
* 完整掃描：指定 --full 或 --write-baseline、上次完整掃描超過 full_scan_max_age_days、
  無紀錄、或無法取得 git 差異時。上次完整掃描日期存於 tools_venv 目錄（不進版控），
  僅在完整掃描無工具錯誤且無未執行項目時更新。

用法：
  python .agents/skills/code-review/scripts/security_scan.py
  python .agents/skills/code-review/scripts/security_scan.py --full
  python .agents/skills/code-review/scripts/security_scan.py --write-baseline --reason "導入前既有發現，待評估" --expires 2027-02-28

結束碼：0 無 P0；1 有 P0、工具缺失或執行錯誤、基準檔格式錯誤；2 專案設定檔缺漏或錯誤。
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(ROOT_DIR / ".agents" / "lib"))
from project_config import ProjectConfigError, load_project_config  # noqa: E402

# 工具輸出中出現以下字樣時，視為無法連網而非執行錯誤
NETWORK_ERROR_MARKERS = (
    "connectionerror", "connection error", "failed to establish", "name resolution",
    "getaddrinfo", "temporary failure", "timed out", "timeout", "network is unreachable",
    "max retries exceeded", "unable to download", "failed to download", "could not resolve",
    "ssl", "proxy",
)


class BaselineError(Exception):
    """基準檔語法或欄位錯誤。"""


@dataclass(frozen=True)
class Finding:
    tool: str
    rule: str
    location: str
    severity: str
    message: str
    fingerprint: str


@dataclass
class ToolOutcome:
    findings: List[Finding] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)   # 無法連網，未執行
    errors: List[str] = field(default_factory=list)    # 工具缺失或執行錯誤
    notes: List[str] = field(default_factory=list)     # 差異掃描下無須執行之說明


@dataclass
class Classification:
    p0: List[Finding] = field(default_factory=list)
    p1: List[Finding] = field(default_factory=list)
    baselined: List[Finding] = field(default_factory=list)
    stale_entries: List[dict] = field(default_factory=list)  # 基準項目已無對應發現，可移除


# ----------------------------------------------------------------------------- 指紋與解析

def _digest(*parts: str) -> str:
    """回傳 'fp' + SHA-256 前 16 碼。固定前綴讓雜湊不緊接在非英數字元之後，
    避免被隱私掃描的證號樣式（如 [A-Z][12]\\d{8}）誤判。"""
    return "fp" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def _rel_posix(path_text: str, root: Path) -> str:
    path = Path(path_text)
    if not path.is_absolute():  # 工具以 root 為工作目錄執行，相對路徑即專案相對路徑
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(path_text).as_posix()


def parse_semgrep(payload: dict, root: Path) -> List[Finding]:
    """Semgrep --json 結果轉為 Finding。指紋 = 規則 + 檔案 + 命中程式碼（去空白），不含行號，避免行號位移造成誤判為新發現。"""
    findings = []
    for result in payload.get("results", []):
        rule = result.get("check_id", "")
        rel = _rel_posix(result.get("path", ""), root)
        extra = result.get("extra", {}) or {}
        code = " ".join(str(extra.get("lines", "")).split())
        line = (result.get("start") or {}).get("line", 0)
        findings.append(Finding(
            tool="semgrep",
            rule=rule,
            location=f"{rel}:{line}",
            severity=str(extra.get("severity", "")).upper(),
            message=" ".join(str(extra.get("message", "")).split())[:200],
            fingerprint=f"semgrep:{_digest(rule, rel, code)}",
        ))
    return findings


def parse_pip_audit(payload: dict, requirement_file: str) -> List[Finding]:
    """pip-audit --format json 結果轉為 Finding。指紋 = 套件 + 版本 + 漏洞編號。"""
    findings = []
    for dep in payload.get("dependencies", []):
        name, version = dep.get("name", ""), dep.get("version", "")
        for vuln in dep.get("vulns", []) or []:
            vuln_id = vuln.get("id", "")
            fixes = ", ".join(vuln.get("fix_versions", []) or []) or "無"
            findings.append(Finding(
                tool="pip-audit",
                rule=vuln_id,
                location=f"{requirement_file}:{name}=={version}",
                severity="DEPENDENCY",
                message=f"{name} {version} 有已知漏洞 {vuln_id}（修正版本：{fixes}）",
                fingerprint=f"pip-audit:{_digest(name.lower(), version, vuln_id)}",
            ))
    return findings


def dedupe(findings: Sequence[Finding]) -> List[Finding]:
    """同一指紋只保留第一筆（pip-audit 可能對同一漏洞重複列出）。"""
    unique: Dict[str, Finding] = {}
    for finding in findings:
        unique.setdefault(finding.fingerprint, finding)
    return list(unique.values())


# ----------------------------------------------------------------------------- 基準檔

def load_baseline(path: Path) -> List[dict]:
    """讀取基準檔；檔案不存在視為空。每筆必填 fingerprint、reason、expires（YYYY-MM-DD）。"""
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as err:
        raise BaselineError(f"基準檔 JSON 格式錯誤: {err}") from err
    entries = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise BaselineError("基準檔須為 {\"findings\": [...]} 結構")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BaselineError(f"基準檔 findings[{index}] 須為物件")
        for key in ("fingerprint", "reason", "expires"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise BaselineError(f"基準檔 findings[{index}] 缺少必填欄位 {key}")
        try:
            dt.date.fromisoformat(entry["expires"])
        except ValueError as err:
            raise BaselineError(f"基準檔 findings[{index}].expires 須為 YYYY-MM-DD") from err
    return entries


def write_baseline(path: Path, existing: List[dict], findings: Sequence[Finding], reason: str, expires: str) -> int:
    """將尚未登錄之發現加入基準檔（保留既有項目），回傳新增筆數。"""
    dt.date.fromisoformat(expires)
    known = {entry["fingerprint"] for entry in existing}
    added = []
    for finding in findings:
        if finding.fingerprint in known:
            continue
        known.add(finding.fingerprint)
        added.append({
            "fingerprint": finding.fingerprint,
            "tool": finding.tool,
            "rule": finding.rule,
            "location": finding.location,
            "reason": reason,
            "expires": expires,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump({"findings": list(existing) + added}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return len(added)


# ----------------------------------------------------------------------------- 判定

def classify(findings: Sequence[Finding], baseline: Sequence[dict], today: dt.date,
             block_severities: Sequence[str], dependency_level: str) -> Classification:
    result = Classification()
    active = {e["fingerprint"]: e for e in baseline if dt.date.fromisoformat(e["expires"]) >= today}
    seen = set()
    blocking = {s.upper() for s in block_severities}
    for finding in findings:
        seen.add(finding.fingerprint)
        if finding.fingerprint in active:
            result.baselined.append(finding)
            continue
        if finding.tool == "pip-audit":
            level = dependency_level
        else:
            level = "P0" if finding.severity in blocking else "P1"
        (result.p0 if level == "P0" else result.p1).append(finding)
    result.stale_entries = [e for e in baseline if e["fingerprint"] not in seen]
    return result


# ----------------------------------------------------------------------------- 執行工具

Runner = Callable[[List[str], Path], Tuple[int, str, str]]


def default_runner(cmd: List[str], cwd: Path) -> Tuple[int, str, str]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    completed = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def resolve_tool(name: str, root: Path, tools_venv: str) -> Optional[str]:
    venv = root / tools_venv
    for candidate in (venv / "Scripts" / f"{name}.exe", venv / "Scripts" / name, venv / "bin" / name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def is_network_error(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in NETWORK_ERROR_MARKERS)


def _parse_json(stdout: str) -> Optional[dict]:
    try:
        data = json.loads(stdout) if stdout and stdout.strip() else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def run_semgrep(tools: dict, root: Path, runner: Runner, targets: Optional[List[str]] = None) -> ToolOutcome:
    """targets 為 None 表示完整掃描 scan_paths；為清單時只掃描這些變更檔（空清單即略過）。"""
    outcome = ToolOutcome()
    if targets is not None and not targets:
        outcome.notes.append("semgrep：scan_paths 內無程式變更，略過")
        return outcome
    exe = resolve_tool("semgrep", root, tools["tools_venv"])
    if exe is None:
        outcome.errors.append("找不到 semgrep，請依 requirements-dev.txt 安裝至 tools_venv")
        return outcome
    if targets is None:
        paths = [p for p in tools["scan_paths"] if (root / p).exists()]
        missing = sorted(set(tools["scan_paths"]) - set(paths))
        if missing:
            outcome.errors.append(f"scan_paths 不存在: {', '.join(missing)}")
    else:
        paths = list(targets)
    if not paths:
        return outcome
    cmd = [exe, "scan", "--json", "--metrics=off", "--quiet"]
    for config in tools["semgrep_configs"]:
        cmd += ["--config", config]
    code, stdout, stderr = runner(cmd + paths, root)
    payload = _parse_json(stdout)
    errors = (payload or {}).get("errors") or []
    error_text = stderr + " " + " ".join(json.dumps(e, ensure_ascii=False) for e in errors)
    if payload is None or (code not in (0, 1) and not payload.get("results")):
        if is_network_error(error_text):
            outcome.skipped.append("semgrep：無法下載規則集（無法連網）")
        else:
            outcome.errors.append(f"semgrep 執行失敗（結束碼 {code}）: {error_text.strip()[:300]}")
        return outcome
    outcome.findings.extend(parse_semgrep(payload, root))
    if errors:
        outcome.errors.append(f"semgrep 回報 {len(errors)} 項掃描錯誤: {json.dumps(errors[0], ensure_ascii=False)[:300]}")
    return outcome


def run_pip_audit(tools: dict, root: Path, runner: Runner, requirement_files: Optional[List[str]] = None) -> ToolOutcome:
    """requirement_files 為 None 表示掃描全部 dependency_files；為清單時只掃描變更的需求檔（空清單即略過）。"""
    outcome = ToolOutcome()
    if requirement_files is not None and not requirement_files:
        outcome.notes.append("pip-audit：需求檔無變更，略過")
        return outcome
    exe = resolve_tool("pip-audit", root, tools["tools_venv"])
    if exe is None:
        outcome.errors.append("找不到 pip-audit，請依 requirements-dev.txt 安裝至 tools_venv")
        return outcome
    for req in (tools["dependency_files"] if requirement_files is None else requirement_files):
        if not (root / req).is_file():
            outcome.errors.append(f"dependency_files 不存在: {req}")
            continue
        code, stdout, stderr = runner([exe, "-r", req, "--format", "json", "--progress-spinner", "off"], root)
        payload = _parse_json(stdout)
        if payload is None:
            if is_network_error(stderr):
                outcome.skipped.append(f"pip-audit {req}：無法查詢漏洞資料庫（無法連網）")
            else:
                outcome.errors.append(f"pip-audit {req} 執行失敗（結束碼 {code}）: {stderr.strip()[-300:]}")
            continue
        outcome.findings.extend(parse_pip_audit(payload, req))
    return outcome


# ----------------------------------------------------------------------------- 觸發方式（決議 10）

STATE_FILE_NAME = ".security_scan_state.json"


def state_path(root: Path, tools: dict) -> Path:
    return root / tools["tools_venv"] / STATE_FILE_NAME


def load_last_full_scan(path: Path) -> Optional[dt.date]:
    """讀取上次完整掃描日期；檔案不存在或內容損壞視為無紀錄。"""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return dt.date.fromisoformat(json.load(handle)["last_full_scan"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_last_full_scan(path: Path, day: dt.date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump({"last_full_scan": day.isoformat()}, handle)
        handle.write("\n")


def changed_files(root: Path, base: str, runner: Runner) -> Optional[List[str]]:
    """回傳相對 base 分支（merge-base 起算）之已提交、未提交與未追蹤變更檔；git 失敗時回傳 None。"""
    code, out, _ = runner(["git", "merge-base", base, "HEAD"], root)
    merge_base = out.strip()
    if code != 0 or not merge_base:
        return None
    code_diff, diff_out, _ = runner(["git", "diff", "--name-only", merge_base], root)
    code_new, new_out, _ = runner(["git", "ls-files", "--others", "--exclude-standard"], root)
    if code_diff != 0 or code_new != 0:
        return None
    names = {line.strip().replace("\\", "/") for line in (diff_out + "\n" + new_out).splitlines() if line.strip()}
    return sorted(n for n in names if (root / n).is_file())  # 已刪除之檔案不掃描


def _within(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def decide_mode(force_full: bool, last_full: Optional[dt.date], today: dt.date, max_age_days: int,
                changed: Optional[List[str]]) -> Tuple[bool, str]:
    """回傳 (是否完整掃描, 原因)。"""
    if force_full:
        return True, "指定完整掃描"
    if last_full is None:
        return True, "本機無完整掃描紀錄"
    if (today - last_full).days > max_age_days:
        return True, f"上次完整掃描 {last_full.isoformat()} 已超過 {max_age_days} 天"
    if changed is None:
        return True, "無法取得 git 差異"
    return False, f"上次完整掃描 {last_full.isoformat()}"


# ----------------------------------------------------------------------------- 主流程

def _print_findings(label: str, findings: Sequence[Finding]) -> None:
    for f in findings:
        print(f"  [{label}] {f.tool} {f.rule} @ {f.location} ({f.severity}) {f.message}")


def scan(root: Path = ROOT_DIR, runner: Runner = default_runner, today: Optional[dt.date] = None,
         write: Optional[Tuple[str, str]] = None, force_full: bool = False) -> int:
    try:
        tools = load_project_config(root, ("security.tools",))["security"]["tools"]
    except ProjectConfigError as err:
        print(f"[FAIL] 專案設定錯誤: {err}")
        return 2
    baseline_path = root / tools["baseline"]
    try:
        baseline = load_baseline(baseline_path)
    except BaselineError as err:
        print(f"[FAIL] {err}")
        return 1

    today = today or dt.date.today()
    forced = force_full or write is not None
    state = state_path(root, tools)
    changed = None if forced else changed_files(root, tools["diff_base"], runner)
    full, reason = decide_mode(forced, load_last_full_scan(state), today,
                               tools["full_scan_max_age_days"], changed)
    if full:
        outcomes = [run_semgrep(tools, root, runner), run_pip_audit(tools, root, runner)]
    else:
        code_targets = [f for f in changed if _within(f, tools["scan_paths"])]
        req_targets = [f for f in changed if f in set(tools["dependency_files"])]
        outcomes = [run_semgrep(tools, root, runner, code_targets),
                    run_pip_audit(tools, root, runner, req_targets)]
    findings = dedupe([f for o in outcomes for f in o.findings])
    skipped = [s for o in outcomes for s in o.skipped]
    errors = [e for o in outcomes for e in o.errors]
    notes = [n for o in outcomes for n in o.notes]
    if full and not skipped and not errors:
        save_last_full_scan(state, today)

    if write is not None:
        added = write_baseline(baseline_path, baseline, findings, *write)
        print(f"[INFO] 已將 {added} 筆新發現寫入基準檔 {tools['baseline']}（請逐筆檢視理由與到期日）")
        baseline = load_baseline(baseline_path)

    result = classify(findings, baseline, today,
                      tools["semgrep_block_severities"], tools["dependency_level"])
    if not full:
        result.stale_entries = []  # 差異掃描未涵蓋全部檔案，無法判斷基準項目是否已失效

    print("=== [security-scan] Gate 2 安全掃描 ===")
    mode = "完整掃描" if full else f"差異掃描（相對 {tools['diff_base']}）"
    print(f"[INFO] 模式：{mode}；{reason}")
    if changed is None and not forced:
        print(f"[WARN] 無法取得相對 {tools['diff_base']} 的 git 差異，改為完整掃描")
    for item in notes:
        print(f"[INFO] {item}")
    for item in skipped:
        print(f"[WARN] 未執行：{item}")
    for item in errors:
        print(f"[FAIL] {item}")
    _print_findings("P0", result.p0)
    _print_findings("P1", result.p1)
    for entry in result.stale_entries:
        print(f"[WARN] 基準項目已無對應發現，可移除: {entry['fingerprint']} {entry.get('rule', '')}")
    print(f"[SUMMARY] P0={len(result.p0)} P1={len(result.p1)} 基準內={len(result.baselined)} "
          f"未執行={len(skipped)} 錯誤={len(errors)}")

    if result.p0 or errors:
        print(">>> [ERROR] 安全掃描未通過：存在 P0 發現或工具執行錯誤 <<<")
        return 1
    print(">>> [SUCCESS] 安全掃描零 P0（P1 須於 Gate 2 Checklist 覆核處置） <<<")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Gate 2 通用安全掃描（Semgrep + pip-audit，Spec-0030）")
    parser.add_argument("--full", action="store_true", help="完整掃描（忽略差異與上次完整掃描日期）")
    parser.add_argument("--write-baseline", action="store_true", help="將目前未登錄之發現寫入基準檔（隱含完整掃描）")
    parser.add_argument("--reason", help="寫入基準檔時之理由（必填）")
    parser.add_argument("--expires", help="寫入基準檔時之到期日 YYYY-MM-DD（必填）")
    args = parser.parse_args(argv)
    write = None
    if args.write_baseline:
        if not (args.reason and args.reason.strip() and args.expires):
            parser.error("--write-baseline 需同時提供 --reason 與 --expires")
        try:
            dt.date.fromisoformat(args.expires)
        except ValueError:
            parser.error("--expires 須為 YYYY-MM-DD")
        write = (args.reason.strip(), args.expires)
    return scan(write=write, force_full=args.full)


if __name__ == "__main__":
    sys.exit(main())
