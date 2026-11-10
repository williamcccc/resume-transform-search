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
5. .claude/ 原生轉接層與 .agents/ 正本一一對應、frontmatter 一致且未複製正本內容。
6. 規格須宣告「品質評測範圍：是/否」；宣告為「是」者，驗收標準須列出品質指標
   （編號 0023 起強制，較早者未宣告則略過、宣告為「是」但缺指標僅警告）。
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

# Claude Code 原生轉接層規則
SKILL_ALIASES = {"code-review": "gate2-code-review"}  # 避免與 Claude Code 內建指令撞名
ADAPTER_MAX_LINES = 20  # 轉接檔行數上限，超過視為複製正本內容


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


def parse_frontmatter(text: str) -> dict[str, str]:
    """解析 Markdown frontmatter 之頂層鍵值（支援 >- / | 多行摺疊），值以單一空白正規化。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, list[str]] = {}
    current = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key_match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if key_match:
            current = key_match.group(1)
            value = key_match.group(2).strip()
            fields[current] = [] if value in (">-", ">", "|", "|-") else [value]
        elif current is not None:
            fields[current].append(line.strip())
    return {k: " ".join(v for v in vals if v) for k, vals in fields.items()}


def _check_adapter(adapter: Path, source: Path, expected_name: str, root: Path) -> bool:
    rel = adapter.relative_to(root).as_posix()
    if not adapter.exists():
        print(f"[FAIL] 缺少 Claude Code 轉接檔: {rel}（正本: {source.relative_to(root).as_posix()}）")
        return False
    text = adapter.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    ok = True
    if meta.get("name") != expected_name:
        print(f"[FAIL] 轉接檔 name 應為 {expected_name!r}，實際為 {meta.get('name')!r}: {rel}")
        ok = False
    if not meta.get("description"):
        print(f"[FAIL] 轉接檔缺少 description: {rel}")
        ok = False
    source_ref = source.relative_to(root).as_posix()
    if source_ref not in text:
        print(f"[FAIL] 轉接檔未指向正本 {source_ref}: {rel}")
        ok = False
    if len(text.splitlines()) > ADAPTER_MAX_LINES:
        print(f"[FAIL] 轉接檔超過 {ADAPTER_MAX_LINES} 行，疑似複製正本內容: {rel}")
        ok = False
    return ok


def check_claude_adapters(root: Path = ROOT_DIR) -> bool:
    """校驗 .agents/ 正本之 Skill 與角色皆有對應之 .claude/ 轉接檔，且無孤兒轉接檔。"""
    agents_dir = root / ".agents"
    skills_src = agents_dir / "skills"
    skills_dst = root / ".claude" / "skills"
    agents_dst = root / ".claude" / "agents"
    if not agents_dir.exists():
        print("[WARN] 未發現 .agents/ 目錄，略過 Claude Code 轉接層校驗")
        return True

    all_ok = True
    expected_skill_dirs = set()
    for source in sorted(skills_src.glob("*/SKILL.md")):
        src_name = source.parent.name
        alias = SKILL_ALIASES.get(src_name, src_name)
        expected_skill_dirs.add(alias)
        adapter = skills_dst / alias / "SKILL.md"
        if not _check_adapter(adapter, source, alias, root):
            all_ok = False
            continue
        src_desc = parse_frontmatter(source.read_text(encoding="utf-8")).get("description")
        dst_desc = parse_frontmatter(adapter.read_text(encoding="utf-8")).get("description")
        if src_desc != dst_desc:
            print(f"[FAIL] 轉接檔 description 與正本不一致: {adapter.relative_to(root).as_posix()}")
            all_ok = False

    expected_roles = set()
    for source in sorted(agents_dir.glob("*/AGENT.md")):
        role = source.parent.name
        expected_roles.add(role)
        if not _check_adapter(agents_dst / f"{role}.md", source, role, root):
            all_ok = False

    if skills_dst.exists():
        for orphan in sorted(d.name for d in skills_dst.iterdir() if d.is_dir() and d.name not in expected_skill_dirs):
            print(f"[FAIL] 孤兒 Skill 轉接檔（無對應正本）: .claude/skills/{orphan}")
            all_ok = False
    if agents_dst.exists():
        for orphan in sorted(f.stem for f in agents_dst.glob("*.md") if f.stem not in expected_roles):
            print(f"[FAIL] 孤兒角色轉接檔（無對應正本）: .claude/agents/{orphan}.md")
            all_ok = False

    if all_ok:
        print(f"[PASS] Claude Code 轉接層與 .agents/ 正本一致 (Skill {len(expected_skill_dirs)} 個、角色 {len(expected_roles)} 個)")
    return all_ok


# 品質評測 Gate 1 檢查（AGENTS.md「品質評測規則」第 1 條）
QUALITY_SCOPE_PATTERN = re.compile(r"品質評測範圍[\s*]*[:：][\s*]*(是|否)")
_NO_ALNUM_BEFORE = r"(?<![A-Za-z0-9])"
_NO_ALNUM_AFTER = r"(?![A-Za-z0-9])"
QUALITY_METRIC_PATTERN = re.compile(
    _NO_ALNUM_BEFORE
    + r"(?:Recall@\w+|Precision@\w+|MRR|nDCG(?:@\w+)?|F1)"
    + _NO_ALNUM_AFTER
    + r"|評審(?:平均)?分數|一致率",
    re.IGNORECASE,
)
QUALITY_AC_ENFORCED_FROM = 23  # 規格編號達此值起須宣告範圍且缺漏標示 FAIL
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


def extract_acceptance_section(text: str) -> str:
    """取出「驗收標準」段落，至下一個同級或更高層級標題為止；忽略程式碼區塊內的 #。
    找不到驗收標題時回傳空字串（不以全文代替）。"""
    in_fence = False
    level = None
    body = []
    for line in text.splitlines():
        if _FENCE_PATTERN.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING_PATTERN.match(line)
        if level is None:
            if heading and len(heading.group(1)) >= 2 and "驗收" in heading.group(2):
                level = len(heading.group(1))
            continue
        if heading and len(heading.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def quality_scope(text: str):
    """回傳規格宣告的品質評測範圍：True（是）、False（否）或 None（未宣告）。"""
    match = QUALITY_SCOPE_PATTERN.search(text)
    if not match:
        return None
    return match.group(1) == "是"


def has_quality_ac(text: str) -> bool:
    return bool(QUALITY_METRIC_PATTERN.search(extract_acceptance_section(text)))


def check_quality_ac_specs(specs: list) -> bool:
    """校驗規格的品質評測範圍宣告與驗收標準中的品質指標。
    編號 >= QUALITY_AC_ENFORCED_FROM：必須宣告範圍；宣告為「是」者缺指標為 FAIL。
    較早的規格：未宣告略過；宣告為「是」但缺指標僅 WARN。"""
    all_ok = True
    scoped = 0
    for name, text in specs:
        match = re.match(r"^(\d{4})-", name)
        enforced = bool(match) and int(match.group(1)) >= QUALITY_AC_ENFORCED_FROM
        scope = quality_scope(text)
        if scope is None:
            if enforced:
                print(f"[FAIL] 規格缺少「品質評測範圍：是/否」宣告: {name}")
                all_ok = False
            continue
        if not scope:
            continue
        scoped += 1
        if has_quality_ac(text):
            continue
        if enforced:
            print(f"[FAIL] 規格宣告屬品質評測範圍，但驗收標準缺少品質指標 (Recall@K、Precision@K、MRR、nDCG、F1、評審分數或一致率): {name}")
            all_ok = False
        else:
            print(f"[WARN] 規格宣告屬品質評測範圍，驗收標準缺少品質指標（舊規格，暫不強制）: {name}")
    if all_ok:
        print(f"[PASS] 品質評測範圍宣告與驗收條件檢查通過（宣告屬範圍之規格 {scoped} 個）")
    return all_ok


def check_quality_ac_directory(dir_path: Path) -> bool:
    if not dir_path.exists():
        return True
    specs = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(dir_path.glob("*.md")) if p.name != "README.md"]
    return check_quality_ac_specs(specs)


def main():
    print("=== [doc-sync] 文檔雙向同步一致性檢驗 ===")
    ok1 = check_basic_docs_exist()
    ok2 = check_adr_sync()
    ok3 = check_directory_docs(DOCS_SPECS_DIR, "需求與技術實作規格 (Specs)", DOCS_README)
    ok4 = check_directory_docs(DOCS_QA_DIR, "QA 實測驗收報告 (QA Reports)", DOCS_README)
    ok5 = check_claude_adapters()
    ok6 = check_quality_ac_directory(DOCS_SPECS_DIR)

    if ok1 and ok2 and ok3 and ok4 and ok5 and ok6:
        print("\n>>> [SUCCESS] 核心文檔、ADR、規格書與 QA 報告檢驗全數合格 (100% In Sync) <<<\n")
        sys.exit(0)
    else:
        print("\n>>> [ERROR] 文檔同步檢驗未通過，請對照檢核清單修復 <<<\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
