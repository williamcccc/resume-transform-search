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
   （自 project.toml [docs].quality_ac_enforced_from 之編號起強制，較早者未宣告則略過、
   宣告為「是」但缺指標僅警告）。
7. docs/bugs/ 缺陷報告比照規格檢查檔名、索引登錄與品質評測範圍宣告。
8. AGENTS.md 分流表連結之 .agents/workflows/ 流程檔皆存在，且流程檔皆有登錄於分流表。
9. docs/templates/ 範本鏡像與 .agents/ 正本內容一致。
10. AGENTS.md 超過行數上限（project.toml [docs].agents_max_lines）時印出警告（不影響結束碼），
    提醒將內容移至流程檔或技能。
11. 規格須宣告「安全評估範圍：是/否」（自 [docs].security_ac_enforced_from 之編號起強制）；
    宣告為「是」者須含 STRIDE 威脅表與至少一條 NFR-* 驗收條件（Spec-0030）。
12. 閉環通用核心檔（安全與非功能需求框架、安全掃描腳本）必須存在，移植時不得刪除。

結束碼：0 通過；1 有 FAIL；2 專案設定檔缺漏或錯誤（含 [security] 特徵與 not_applicable 理由）。
"""

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(ROOT_DIR / ".agents" / "lib"))
from project_config import ProjectConfigError, load_project_config  # noqa: E402

try:
    # [security]、[project] 一併驗證：缺鍵、型別錯誤或 not_applicable 缺理由時以結束碼 2 中止（Spec-0030 AC-2、Spec-0038）
    PROJECT_CONFIG = load_project_config(ROOT_DIR, ("docs", "security", "security.tools", "project"))
    DOCS_CONFIG = PROJECT_CONFIG["docs"]
except ProjectConfigError as _config_err:
    print(f"[FAIL] 專案設定錯誤: {_config_err}")
    sys.exit(2)

DOCS_DIR = ROOT_DIR / "docs"
DOCS_ADR_DIR = DOCS_DIR / "adr"
DOCS_SPECS_DIR = DOCS_DIR / "specs"
DOCS_QA_DIR = DOCS_DIR / "qa_reports"
DOCS_BUGS_DIR = DOCS_DIR / "bugs"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"
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
        # 新專案尚無此類文件時目錄為空、不進版控（git 不追蹤空目錄），乾淨 checkout 下不存在屬正常（Spec-0045）
        print(f"[WARN] 尚無{doc_type_name}，目錄不存在: {dir_path.relative_to(ROOT_DIR)}")
        return True

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
QUALITY_AC_ENFORCED_FROM = DOCS_CONFIG["quality_ac_enforced_from"]  # 規格編號達此值起須宣告範圍且缺漏標示 FAIL
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
    """回傳規格宣告的品質評測範圍：True（是）、False（否）或 None（未宣告）。
    優先採用驗收標準段落內的宣告；段落內沒有時才退回全文第一個宣告，
    避免正文引用宣告字樣（如說明文字或發現表）被誤當成宣告。"""
    match = QUALITY_SCOPE_PATTERN.search(extract_acceptance_section(text)) or QUALITY_SCOPE_PATTERN.search(text)
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


def _read_specs(dir_path: Path) -> list:
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(dir_path.glob("*.md")) if p.name != "README.md"]


def check_quality_ac_directory(dir_path: Path) -> bool:
    if not dir_path.exists():
        return True
    return check_quality_ac_specs(_read_specs(dir_path))


# 安全與非功能需求 Gate 1 檢查（Spec-0030；框架見 feature-design/references/security_nfr_framework.md）
SECURITY_SCOPE_PATTERN = re.compile(r"安全評估範圍[\s*]*[:：][\s*]*(是|否)")
# 威脅列：表頭含「STRIDE」之欄，其儲存格只含單一 STRIDE 字母（可加粗）；欄位置不限（Spec-0048）
STRIDE_CELL_PATTERN = re.compile(r"^\**\s*[STRIDE]\s*\**$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^:?-{3,}:?$")
NFR_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])NFR-\d+")
SECURITY_AC_ENFORCED_FROM = DOCS_CONFIG["security_ac_enforced_from"]


def _table_cells(line: str) -> list:
    """Markdown 表格列之儲存格（去除首尾 `|`；保留跳脫之 `\\|`）。"""
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def markdown_tables(text: str) -> list:
    """文中所有 Markdown 表格：每表為 (表頭儲存格, 資料列儲存格清單)；第 2 列須為分隔列。"""
    tables, block = [], []
    for line in text.splitlines() + [""]:
        if line.lstrip().startswith("|"):
            block.append(_table_cells(line))
            continue
        if len(block) >= 2 and block[1] and all(TABLE_SEPARATOR_PATTERN.match(c) for c in block[1]):
            tables.append((block[0], block[2:]))
        block = []
    return tables


def has_threat_table(text: str) -> bool:
    """至少一個威脅列：表頭含「STRIDE」之欄，該欄儲存格只含單一 S/T/R/I/D/E 字母（Spec-0048）。"""
    for header, rows in markdown_tables(text):
        columns = [i for i, name in enumerate(header) if "STRIDE" in name]
        for row in rows:
            if any(i < len(row) and STRIDE_CELL_PATTERN.match(row[i]) for i in columns):
                return True
    return False


def security_scope(text: str):
    """回傳安全評估範圍：True（是）、False（否）或 None（未宣告）；優先採驗收標準段落內的宣告。"""
    match = SECURITY_SCOPE_PATTERN.search(extract_acceptance_section(text)) or SECURITY_SCOPE_PATTERN.search(text)
    if not match:
        return None
    return match.group(1) == "是"


def check_security_ac_specs(specs: list, enforced_from: int = None) -> bool:
    """編號 >= enforced_from 之規格：必須宣告安全評估範圍；宣告為「是」者須含 STRIDE 威脅表與 NFR-*。
    較早的規格不檢查（不回溯）。"""
    enforced_from = SECURITY_AC_ENFORCED_FROM if enforced_from is None else enforced_from
    all_ok = True
    scoped = 0
    for name, text in specs:
        match = re.match(r"^(\d{4})-", name)
        if not match or int(match.group(1)) < enforced_from:
            continue
        scope = security_scope(text)
        if scope is None:
            print(f"[FAIL] 規格缺少「安全評估範圍：是/否」宣告: {name}")
            all_ok = False
            continue
        if not scope:
            continue
        scoped += 1
        if not has_threat_table(text):
            print(f"[FAIL] 規格宣告屬安全評估範圍，但缺少 STRIDE 威脅表（表頭須有 STRIDE 欄，且至少一列該欄標註 S/T/R/I/D/E）: {name}")
            all_ok = False
        if not NFR_ID_PATTERN.search(text):
            print(f"[FAIL] 規格宣告屬安全評估範圍，但缺少 NFR-* 非功能驗收條件: {name}")
            all_ok = False
    if all_ok:
        print(f"[PASS] 安全評估範圍宣告與威脅建模檢查通過（自編號 {enforced_from:04d} 起強制；宣告屬範圍之規格 {scoped} 個）")
    return all_ok


def check_security_ac_directory(dir_path: Path) -> bool:
    if not dir_path.exists():
        return True
    return check_security_ac_specs(_read_specs(dir_path))


# 閉環通用核心檔：不帶專案專屬標記，移植時不得刪除（Spec-0030 AC-1；Spec-0034 C6 擴充）
CORE_FILES = (
    Path(".agents/skills/feature-design/references/security_nfr_framework.md"),
    Path(".agents/skills/code-review/scripts/security_scan.py"),
    Path(".agents/skills/feature-design/references/arch_review_checklist.md"),
    Path(".agents/skills/code-review/references/review_checklist.md"),
)


def check_core_files(root: Path = ROOT_DIR, core_files: tuple = CORE_FILES) -> bool:
    missing = [p.as_posix() for p in core_files if not (root / p).is_file()]
    for path in missing:
        print(f"[FAIL] 閉環通用核心檔缺失（移植時不得刪除）: {path}")
    if not missing:
        print(f"[PASS] 閉環通用核心檔齊備 ({len(core_files)} 個)")
    return not missing


# ---------------------------------------------------------------- 閉環結構檢查（Spec-0034）

FRAMEWORK_FILE = Path(".agents/skills/feature-design/references/security_nfr_framework.md")
ASVS_CHAPTER_COUNT = 17  # OWASP ASVS 5.0：V1–V17；新版發布時以規範變更更新
ASVS_ROW_PATTERN = re.compile(r"^\|\s*V(\d+)\s*\|[^|]*\|([^|]*)\|", re.MULTILINE)
ASVS_CONDITION_KINDS = ("一律", "特徵", "技術")
CHAPTER_REF_PATTERN = re.compile(r"\bV(\d+)\b")

# 核心與實例之間的契約：核心檔以「見專案概況」「本專案標準見實例檔」引用之檔案（C5）
REQUIRED_INSTANCE_FILES = (
    Path(".agents/project/profile.md"),
    Path(".agents/project/arch_review_criteria.md"),
    Path(".agents/project/review_criteria.md"),
)

PROJECT_MARKER = "<!-- 專案專屬"
# C7：唯一允許之專屬標記位置（AGENTS.md「本專案紅線」小節標題）
ALLOWED_MARKER_LINE_PREFIX = "#### 本專案紅線"
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")


def check_asvs_chapter_coverage(framework_text: str, security: dict) -> bool:
    """C1–C4：ASVS 對照表 V1–V17 各一列、適用條件屬三類之一、技術章節皆已宣告、not_applicable 編號在範圍內。"""
    ok = True
    section = framework_text.split("## 四、", 1)[1].split("\n## ", 1)[0] if "## 四、" in framework_text else ""
    rows = [(int(num), cond.strip()) for num, cond in ASVS_ROW_PATTERN.findall(section)]
    numbers = [num for num, _ in rows]
    expected = list(range(1, ASVS_CHAPTER_COUNT + 1))
    missing = sorted(set(expected) - set(numbers))
    duplicated = sorted({n for n in numbers if numbers.count(n) > 1})
    extra = sorted(set(numbers) - set(expected))
    if missing or duplicated or extra:
        ok = False
        print(f"[FAIL] ASVS 對照表章節不符 V1–V{ASVS_CHAPTER_COUNT}：缺 {missing}、重複 {duplicated}、超出範圍 {extra}")
    for num, cond in rows:
        if not cond.startswith(ASVS_CONDITION_KINDS):
            ok = False
            print(f"[FAIL] ASVS V{num} 適用條件未歸屬「一律／特徵／技術」：{cond}")

    declared_na = set()
    for entry in security.get("not_applicable", []):
        refs = [int(n) for n in CHAPTER_REF_PATTERN.findall(entry.get("item", ""))]
        out_of_range = [n for n in refs if n not in expected]
        if out_of_range:
            ok = False
            print(f"[FAIL] not_applicable 提及 ASVS 範圍外章節 {['V%d' % n for n in out_of_range]}：{entry.get('item')}")
        declared_na.update(refs)
    in_use = set()
    for ref in security.get("tech_chapters_in_use", []):
        match = re.fullmatch(r"V(\d+)", ref.strip())
        if not match or int(match.group(1)) not in expected:
            ok = False
            print(f"[FAIL] tech_chapters_in_use 含無效章節：{ref}")
            continue
        in_use.add(int(match.group(1)))
    tech = [num for num, cond in rows if cond.startswith("技術")]
    for num in tech:
        if num not in in_use and num not in declared_na:
            ok = False
            print(f"[FAIL] ASVS V{num} 為技術條件章節，未於 tech_chapters_in_use 或 not_applicable 宣告")
        elif num in in_use and num in declared_na:
            ok = False
            print(f"[FAIL] ASVS V{num} 同時列於 tech_chapters_in_use 與 not_applicable")
    if ok:
        print(f"[PASS] ASVS 章節歸屬完整（{len(rows)} 章；技術條件章節 {len(tech)} 章皆已宣告）")
    return ok


def check_required_instance_files(root: Path = ROOT_DIR, files: tuple = REQUIRED_INSTANCE_FILES) -> bool:
    """C5：核心引用之專案實例檔必須存在。"""
    missing = [p.as_posix() for p in files if not (root / p).is_file()]
    for path in missing:
        print(f"[FAIL] 專案實例檔缺失（移植時整份替換，不得刪除）: {path}")
    if not missing:
        print(f"[PASS] 專案實例檔齊備 ({len(files)} 個)")
    return not missing


def find_project_markers(text: str) -> list:
    """回傳專屬標記所在之 (行號, 行)；排除程式碼區塊與行內程式碼（說明文字）。"""
    hits, fence = [], None
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE_PATTERN.match(line)
        if match:
            marker = match.group(1)[0]
            fence = None if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        if PROJECT_MARKER in INLINE_CODE_PATTERN.sub("", line):
            hits.append((number, line))
    return hits


def check_project_markers(root: Path = ROOT_DIR) -> bool:
    """C7：AGENTS.md 與 .agents/**/*.md（不含 project/）只允許「本專案紅線」小節標題 1 處專屬標記。"""
    agents_dir = root / ".agents"
    files = [root / "AGENTS.md"]
    if agents_dir.is_dir():
        files += sorted(p for p in agents_dir.rglob("*.md") if p.relative_to(agents_dir).parts[0] != "project")
    ok, allowed = True, 0
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        for number, line in find_project_markers(path.read_text(encoding="utf-8")):
            if rel == "AGENTS.md" and line.startswith(ALLOWED_MARKER_LINE_PREFIX):
                allowed += 1
                continue
            ok = False
            print(f"[FAIL] 通用核心出現專案專屬標記（應移至 .agents/project/ 或 AGENTS.md 本專案紅線）: {rel}:{number}")
    if allowed != 1:
        ok = False
        print(f"[FAIL] AGENTS.md「本專案紅線」小節標題之專屬標記應恰好 1 處，實際 {allowed} 處")
    if ok:
        print("[PASS] 專屬標記只位於 AGENTS.md「本專案紅線」小節（1 處）")
    return ok


def check_business_skills(skills: list, root: Path = ROOT_DIR) -> bool:
    """C8：project.business_skills 每項於 .agents/skills/ 與 .claude/skills/ 皆有同名資料夾。"""
    ok = True
    for skill in skills:
        for base in (".agents/skills", ".claude/skills"):
            if not (root / base / skill).is_dir():
                ok = False
                print(f"[FAIL] business_skills 列出之技能不存在: {base}/{skill}")
    if ok:
        print(f"[PASS] 業務技能清單與技能資料夾一致 ({len(skills)} 個)")
    return ok


# 流程分軌檢查（AGENTS.md 第 2 節分流表 ↔ .agents/workflows/）
WORKFLOW_LINK_PATTERN = re.compile(r"\]\((?:\./)?(\.agents/workflows/[^)\s#]+\.md)(?:#[^)]*)?\)")


def check_workflow_routing(agents_text: str, root: Path = ROOT_DIR) -> bool:
    """校驗分流表連結之流程檔皆存在，且 .agents/workflows/ 下每個流程檔皆有登錄。"""
    linked = set(WORKFLOW_LINK_PATTERN.findall(agents_text))
    workflows_dir = root / ".agents" / "workflows"
    existing = (
        {p.relative_to(root).as_posix() for p in workflows_dir.glob("*.md")}
        if workflows_dir.exists()
        else set()
    )
    all_ok = True
    if not linked:
        print("[FAIL] AGENTS.md 分流表未連結任何 .agents/workflows/ 流程檔")
        return False
    for link in sorted(linked - existing):
        print(f"[FAIL] AGENTS.md 分流表連結之流程檔不存在: {link}")
        all_ok = False
    for orphan in sorted(existing - linked):
        print(f"[FAIL] 流程檔未登錄於 AGENTS.md 分流表: {orphan}")
        all_ok = False
    if all_ok:
        print(f"[PASS] AGENTS.md 分流表與 .agents/workflows/ 流程檔一致 ({len(linked)} 個)")
    return all_ok


# docs/templates/ 鏡像：檔名 → 正本相對路徑
TEMPLATE_MIRRORS = {
    "prd_template.md": ".agents/skills/feature-design/references/prd_template.md",
    "tech_spec_template.md": ".agents/skills/feature-design/references/tech_spec_template.md",
    "test_case_template.md": ".agents/skills/qa-testing/references/test_case_template.md",
    "qa_report_template.md": ".agents/skills/qa-testing/references/qa_report_template.md",
    "bug_report_template.md": ".agents/skills/bug-triage/references/bug_report_template.md",
}


def _normalized(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check_template_mirrors(root: Path = ROOT_DIR, mirrors: dict = TEMPLATE_MIRRORS) -> bool:
    """校驗 docs/templates/ 鏡像與 .agents/ 正本內容一致（忽略換行符差異）。"""
    all_ok = True
    for name, source_rel in mirrors.items():
        mirror = root / "docs" / "templates" / name
        source = root / source_rel
        if not source.exists():
            print(f"[FAIL] 範本正本不存在: {source_rel}")
            all_ok = False
        elif not mirror.exists():
            print(f"[FAIL] 缺少範本鏡像: docs/templates/{name}（正本: {source_rel}）")
            all_ok = False
        elif _normalized(mirror) != _normalized(source):
            print(f"[FAIL] 範本鏡像與正本不一致，請自正本複製: docs/templates/{name} ← {source_rel}")
            all_ok = False
    if all_ok:
        print(f"[PASS] docs/templates/ 範本鏡像與正本一致 ({len(mirrors)} 個)")
    return all_ok


# AGENTS.md 常駐載入，行數過多會讓每次對話都多付 Token（governance.md G4 第 4 項）
AGENTS_MAX_LINES = DOCS_CONFIG["agents_max_lines"]


def check_agents_size(agents_text: str, max_lines: int = AGENTS_MAX_LINES) -> bool:
    """AGENTS.md 超過行數上限時印出 WARN；僅提醒，一律回傳 True。"""
    lines = len(agents_text.splitlines())
    if lines > max_lines:
        print(
            f"[WARN] AGENTS.md 共 {lines} 行，超過上限 {max_lines} 行；"
            "AGENTS.md 每次對話皆自動載入，請考慮將內容移至 .agents/workflows/ 或技能"
        )
    else:
        print(f"[PASS] AGENTS.md 共 {lines} 行（上限 {max_lines} 行）")
    return True


def main():
    print("=== [doc-sync] 文檔雙向同步一致性檢驗 ===")
    ok1 = check_basic_docs_exist()
    ok2 = check_adr_sync()
    ok3 = check_directory_docs(DOCS_SPECS_DIR, "需求與技術實作規格 (Specs)", DOCS_README)
    ok4 = check_directory_docs(DOCS_QA_DIR, "QA 實測驗收報告 (QA Reports)", DOCS_README)
    ok5 = check_claude_adapters()
    ok6 = check_quality_ac_directory(DOCS_SPECS_DIR)
    ok7 = check_directory_docs(DOCS_BUGS_DIR, "缺陷報告 (Bug Reports)", DOCS_README)
    ok8 = check_quality_ac_directory(DOCS_BUGS_DIR)
    agents_text = AGENTS_FILE.read_text(encoding="utf-8") if AGENTS_FILE.exists() else ""
    ok9 = check_workflow_routing(agents_text)
    ok10 = check_template_mirrors()
    ok11 = check_security_ac_directory(DOCS_SPECS_DIR)
    ok12 = check_core_files()
    framework = ROOT_DIR / FRAMEWORK_FILE
    framework_text = framework.read_text(encoding="utf-8") if framework.is_file() else ""
    ok13 = check_asvs_chapter_coverage(framework_text, PROJECT_CONFIG["security"])
    ok14 = check_required_instance_files()
    ok15 = check_project_markers()
    ok16 = check_business_skills(PROJECT_CONFIG["project"]["business_skills"])
    check_agents_size(agents_text)

    if all((ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8, ok9, ok10, ok11, ok12, ok13, ok14, ok15, ok16)):
        print("\n>>> [SUCCESS] 核心文檔、ADR、規格書與 QA 報告檢驗全數合格 (100% In Sync) <<<\n")
        sys.exit(0)
    else:
        print("\n>>> [ERROR] 文檔同步檢驗未通過，請對照檢核清單修復 <<<\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
