"""
閉環移植演練多組參數化（Spec-0046）

將閉環核心移植至暫存假專案，於數種實例設定變體下執行核心自我測試、verify_doc_sync.py 與
audit_guardrails.py，揭露核心測試對原專案實例值之假設（如層名、範本檔名、分層開關、本專案紅線內容、非空清單）。
不修改專案本身的任何檔案；假專案內容全為合成資料。安全掃描不在本檔範圍（見 test_portable_closed_loop_e2e.py）。
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = (
    ".agents/skills/feature-design/references/prd_template.md",
    ".agents/skills/feature-design/references/tech_spec_template.md",
    ".agents/skills/qa-testing/references/test_case_template.md",
    ".agents/skills/qa-testing/references/qa_report_template.md",
    ".agents/skills/bug-triage/references/bug_report_template.md",
)
LITERAL_KEYS = {"api_key_patterns", "identifiers", "stack_terms"}
RED_LINES = (
    "#### 本專案紅線（移植時整節改寫）<!-- 專案專屬：整節 -->\n"
    "* **紅線 8｜示範紅線**：示範專案之業務約束。\n"
    "* **本專案執行環境**：Python 3.13。\n\n"
)


# ---------- project.toml 區段感知改寫 ----------
def _value(key, value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        quote = (lambda v: f"'{v}'") if key in LITERAL_KEYS else (lambda v: json.dumps(v, ensure_ascii=False))
        return "[" + ", ".join(quote(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def _depth(text):
    depth, quote = 0, None
    for ch in text:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#":
            break
        else:
            depth += (ch == "[") - (ch == "]")
    return depth


def _bounds(lines, section):
    start = lines.index(f"[{section}]")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    return start, end


def set_key(text, section, key, value):
    lines = text.split("\n")
    start, end = _bounds(lines, section)
    for i in range(start + 1, end):
        if re.match(rf"^{re.escape(key)}\s*=", lines[i]):
            j, depth = i, _depth(lines[i].split("=", 1)[1])
            while depth > 0:
                j += 1
                depth += _depth(lines[j])
            lines[i:j + 1] = [f"{key} = {_value(key, value)}"]
            return "\n".join(lines)
    raise KeyError(f"[{section}].{key}")


def clear_table_array(text, parent, key):
    """刪除 [[parent.key]] 表格並於父區段內寫 key = []（PORTING 第 3 步）。"""
    out, skip = [], False
    for line in text.split("\n"):
        if line.strip() == f"[[{parent}.{key}]]":
            skip = True
            continue
        if skip and line.startswith("["):
            skip = False
        if not skip:
            out.append(line)
    start, end = _bounds(out, parent)
    while end > start + 1 and not out[end - 1].strip():
        end -= 1
    out.insert(end, f"{key} = []")
    return "\n".join(out)


# ---------- 變體 ----------
def _ddd_files(src, names, config_module, env_file):
    d, a, i, f = names
    pkg = src.replace("/", ".")
    files = {f"{src}/__init__.py": "", config_module: 'import os\n\nTOKEN = os.environ.get("DEMO_TOKEN", "")\n',
             env_file: "DEMO_TOKEN=\n", ".gitignore": ".env\n", "requirements.txt": ""}
    for n in names:
        files[f"{src}/{n}/__init__.py"] = ""
    files[f"{src}/{d}/entity.py"] = "from dataclasses import dataclass\n\n\n@dataclass\nclass Thing:\n    key: str\n"
    files[f"{src}/{a}/use_case.py"] = f"from {pkg}.{d}.entity import Thing\n\n\ndef make(key: str) -> Thing:\n    return Thing(key)\n"
    return files


def _common(config):
    """各變體共用：清除原專案指紋與例外、門檻自 1 起、掃描範圍改為假專案。"""
    config.setdefault("privacy", {})["forbidden_hash_prefixes"] = []
    config.setdefault("project", {})["business_skills"] = []
    config.setdefault("docs", {}).update({"quality_ac_enforced_from": 1, "security_ac_enforced_from": 1})
    config.setdefault("guardrails", {}).setdefault("required_gitignore", [".env"])
    return config


VARIANTS = {
    "逐步導入": {
        "files": {"lib/__init__.py": "", "lib/config.py": 'import os\n\nLEVEL = os.environ.get("CALC_LEVEL", "")\n',
                  ".env.example": "CALC_LEVEL=\n", ".gitignore": ".env\n", "requirements.txt": ""},
        "config": _common({
            "layers": {"enabled": False, "src": "lib", "domain": "lib/domain", "application": "lib/application",
                       "infrastructure": "lib/infrastructure", "interfaces": "lib/interfaces",
                       "domain_interfaces": "lib/domain/interfaces.py"},
            "config": {"module": "lib/config.py", "env_example": ".env.example"},
            "project": {"identifiers": ["WidgetCalc"], "stack_terms": []},
            "security.tools": {"scan_paths": ["lib"], "dependency_files": ["requirements.txt"]},
        }),
    },
    "清單全空": {
        "files": _ddd_files("app", ("domain", "application", "infrastructure", "interfaces"),
                            "app/infrastructure/config.py", ".env.example"),
        "config": _common({
            "layers": {"enabled": True, "src": "app", "domain": "app/domain", "application": "app/application",
                       "infrastructure": "app/infrastructure", "interfaces": "app/interfaces",
                       "domain_interfaces": "app/domain/interfaces.py"},
            "config": {"module": "app/infrastructure/config.py", "env_example": ".env.example"},
            "guardrails": {"url_schemes": [], "api_key_patterns": [], "prompt_indicators": [], "eval_only_modules": [],
                           "required_gitignore": [".env"]},
            "privacy": {"safe_filename_stems": [], "sensitive_dirs": [], "sensitive_extensions": [],
                        "personal_filename_keywords": [], "locale_patterns": []},
            "project": {"identifiers": [], "stack_terms": []},
            "security": {"tech_chapters_in_use": ["V9", "V10", "V17"]},
            "security.tools": {"scan_paths": ["app"], "dependency_files": ["requirements.txt"]},
        }),
        "clear_not_applicable": True,
    },
    "非預設佈局": {
        "files": dict(_ddd_files("service", ("model", "usecases", "adapters", "api"), "settings.py", ".env.sample")),
        "config": _common({
            "layers": {"enabled": True, "src": "service", "domain": "service/model", "application": "service/usecases",
                       "infrastructure": "service/adapters", "interfaces": "service/api",
                       "domain_interfaces": "service/model/ports.py"},
            "config": {"module": "settings.py", "env_example": ".env.sample"},
            "project": {"identifiers": [r"\bservice/"], "stack_terms": ["DemoDB"]},
            "security.tools": {"scan_paths": ["service", "settings.py"], "dependency_files": ["requirements.txt"]},
        }),
    },
}


def port(root: Path, variant: dict) -> None:
    for rel, content in variant["files"].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content, encoding="utf-8")
    ignore = shutil.ignore_patterns("__pycache__")
    for name in (".agents", ".claude"):
        shutil.copytree(PROJECT_ROOT / name, root / name, ignore=ignore)
    for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        shutil.copy2(PROJECT_ROOT / name, root / name)
    config_path = root / ".agents" / "project.toml"
    original = tomllib.loads(config_path.read_text(encoding="utf-8"))
    for skill in original["project"]["business_skills"]:
        shutil.rmtree(root / ".agents" / "skills" / skill)
        shutil.rmtree(root / ".claude" / "skills" / skill)
    text = config_path.read_text(encoding="utf-8")
    for section, values in variant["config"].items():
        for key, value in values.items():
            text = set_key(text, section, key, value)
    text = clear_table_array(text, "guardrails", "url_exceptions")
    if variant.get("clear_not_applicable"):
        text = clear_table_array(text, "security", "not_applicable")
    config_path.write_text(text, encoding="utf-8")
    project = root / ".agents" / "project"
    (project / "security_baseline.json").write_text('{"findings": []}\n', encoding="utf-8")
    for name in ("profile.md", "arch_review_criteria.md", "review_criteria.md"):
        (project / name).write_text("# 示範專案實例檔\n", encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    agents, count = re.subn(r"^#### 本專案紅線.*?(?=^---$)", lambda _: RED_LINES, agents, count=1, flags=re.M | re.S)
    assert count == 1
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    for sub in ("adr", "templates"):
        (root / "docs" / sub).mkdir(parents=True, exist_ok=True)
    for rel in TEMPLATES:
        shutil.copy2(root / rel, root / "docs" / "templates" / Path(rel).name)
    (root / "docs" / "README.md").write_text("# 文件索引\n", encoding="utf-8")
    (root / "docs" / "adr" / "README.md").write_text("# ADR 索引\n", encoding="utf-8")
    (root / "REQUIREMENTS.md").write_text("# 需求\n", encoding="utf-8")
    (root / "ARCHITECTURE.md").write_text("# 架構\n", encoding="utf-8")


def run(root: Path, *args):
    proc = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", timeout=600)
    return proc.returncode, proc.stdout + proc.stderr


class TestPortableVariants(unittest.TestCase):
    def test_core_passes_under_instance_variants(self):
        for name, variant in VARIANTS.items():
            with self.subTest(variant=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "demo_proj"
                root.mkdir()
                port(root, variant)
                for label, args in (
                    ("verify_doc_sync", (".agents/skills/doc-sync/scripts/verify_doc_sync.py",)),
                    ("audit_guardrails", (".agents/skills/code-review/scripts/audit_guardrails.py",)),
                    ("core_self_tests", ("-m", "unittest", "discover", "-s", ".agents/tests", "-p", "test_*.py")),
                ):
                    code, out = run(root, *args)
                    self.assertEqual(code, 0, f"[{name}] {label}\n{out[-3000:]}")

    def test_toml_editor_handles_multiline_arrays_and_table_arrays(self):
        text = (
            "[guardrails]\nurl_schemes = [\n    \"a\",\n    'x]y',\n]\nkeep = 1\n\n"
            "[[guardrails.url_exceptions]]\npath = \"p\"\nreason = \"r\"\n\n[privacy]\nz = 2\n"
        )
        text = set_key(text, "guardrails", "url_schemes", [])
        text = clear_table_array(text, "guardrails", "url_exceptions")
        data = tomllib.loads(text)
        self.assertEqual(data["guardrails"], {"url_schemes": [], "keep": 1, "url_exceptions": []})
        self.assertEqual(data["privacy"], {"z": 2})


if __name__ == "__main__":
    unittest.main()
