"""核心文件內部連結守護測試（Spec-0044）。

核心 Markdown（AGENTS.md、CLAUDE.md、GEMINI.md、.agents/**、.claude/**，業務技能除外）之相對連結，
凡指向核心範圍內者必須存在；指向核心以外（`docs/`、專案根目錄文件、原始碼）者屬專案側，不檢查。
移植只複製核心，專案側斷鏈測試不隨行；本測試隨 `.agents/` 移植，於新專案中守護核心連結完整。
只讀取版控中的規範文件，不讀取本機敏感目錄（`privacy.sensitive_dirs`）。屬閉環核心自我測試，移植後仍須通過。
"""
import re
import tempfile
import unittest
from pathlib import Path

from test_neutral_examples import AGENTS_DIR, PROJECT_ROOT, TOP_LEVEL_DOCS, core_markdown_files

LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _is_core(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return rel.parts[:1] in ((".agents",), (".claude",)) or (len(rel.parts) == 1 and rel.name in TOP_LEVEL_DOCS)


def broken_core_links(files, root: Path) -> list:
    """回傳 (檔案相對路徑, 連結目標) 清單：目標位於核心範圍內卻不存在者。"""
    broken = []
    for path in files:
        text = INLINE_CODE.sub("", FENCE.sub("", path.read_text(encoding="utf-8")))
        for match in LINK.finditer(text):
            target = match.group(1).split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue  # 錨點、http(s)、mailto 等
            resolved = (path.parent / target).resolve()
            if _is_core(resolved, root.resolve()) and not resolved.exists():
                broken.append((path.relative_to(root).as_posix(), match.group(1)))
    return broken


class TestCoreLinks(unittest.TestCase):
    def test_core_markdown_links_resolve(self):
        self.assertEqual(broken_core_links(core_markdown_files(), PROJECT_ROOT), [])

    def test_detects_missing_core_target_and_ignores_project_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agents" / "skills" / "demo").mkdir(parents=True)
            (root / "AGENTS.md").write_text("# 規範\n", encoding="utf-8")
            doc = root / ".agents" / "skills" / "demo" / "SKILL.md"
            doc.write_text(
                "[正本](../../../AGENTS.md)、[缺檔](../missing/SKILL.md)、[選用](../../../GEMINI.md)\n"
                "[規格](../../../docs/specs/x.md)、[網站](https://example.com)、[錨點](#a)\n"
                "`[碼內](../nowhere.md)`\n",
                encoding="utf-8",
            )
            self.assertEqual(
                broken_core_links([doc], root),
                [(".agents/skills/demo/SKILL.md", "../missing/SKILL.md"),
                 (".agents/skills/demo/SKILL.md", "../../../GEMINI.md")],
            )

    def test_scope_matches_neutral_guard(self):
        files = {p.relative_to(PROJECT_ROOT).as_posix() for p in core_markdown_files()}
        self.assertIn(".agents/PORTING.md", files)
        self.assertTrue(all(f.endswith(".md") for f in files))
        self.assertTrue((AGENTS_DIR / "PORTING.md").is_file())


if __name__ == "__main__":
    unittest.main()
