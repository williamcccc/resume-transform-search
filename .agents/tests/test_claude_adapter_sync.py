# -*- coding: utf-8 -*-
"""verify_doc_sync.check_claude_adapters 之白箱單元測試（暫存目錄動態建構，零讀取真實專案檔案）。"""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".agents" / "skills" / "doc-sync" / "scripts" / "verify_doc_sync.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_doc_sync", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SKILL_SOURCE = "---\nname: {name}\ndescription: >-\n  Use this skill to do {name}\n  in two lines.\n---\n\n# body\n"


def _skill_adapter(alias: str, src: str, desc: str | None = None, extra_lines: int = 0) -> str:
    desc_block = desc if desc is not None else f">-\n  Use this skill to do {src}\n  in two lines."
    return (
        f"---\nname: {alias}\ndescription: {desc_block}\n---\n\n"
        f"讀取 `.agents/skills/{src}/SKILL.md` 並依其指示執行。\n" + "x\n" * extra_lines
    )


def _role_adapter(role: str, pointer: bool = True) -> str:
    ref = f"`.agents/{role}/AGENT.md`" if pointer else "角色手冊"
    return f"---\nname: {role}\ndescription: {role} role\nmodel: opus\n---\n\n僅以 Read 讀取 {ref}。\n"


class TestClaudeAdapterSync(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    # ---- Arrange helpers ----
    def _write(self, rel: str, content: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _build_valid_tree(self):
        for name in ("feature-design", "code-review"):
            self._write(f".agents/skills/{name}/SKILL.md", SKILL_SOURCE.format(name=name))
        self._write(".claude/skills/feature-design/SKILL.md", _skill_adapter("feature-design", "feature-design"))
        self._write(".claude/skills/gate2-code-review/SKILL.md", _skill_adapter("gate2-code-review", "code-review"))
        self._write(".agents/gatekeeper/AGENT.md", "# Gatekeeper\n")
        self._write(".claude/agents/gatekeeper.md", _role_adapter("gatekeeper"))

    def _run(self) -> tuple[bool, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = self.mod.check_claude_adapters(self.root)
        return result, buf.getvalue()

    # ---- Positive ----
    def test_valid_tree_passes_with_alias(self):
        self._build_valid_tree()
        ok, out = self._run()
        self.assertTrue(ok, out)
        self.assertIn("Skill 2 個、角色 1 個", out)

    def test_missing_agents_dir_is_skipped(self):
        ok, out = self._run()
        self.assertTrue(ok)
        self.assertIn("[WARN]", out)

    def test_parse_frontmatter_folded_description(self):
        meta = self.mod.parse_frontmatter(SKILL_SOURCE.format(name="demo"))
        self.assertEqual(meta["name"], "demo")
        self.assertEqual(meta["description"], "Use this skill to do demo in two lines.")

    def test_parse_frontmatter_without_header_returns_empty(self):
        self.assertEqual(self.mod.parse_frontmatter("# no frontmatter\n"), {})

    # ---- Negative ----
    def test_missing_skill_adapter_fails(self):
        self._build_valid_tree()
        (self.root / ".claude/skills/feature-design/SKILL.md").unlink()
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("缺少 Claude Code 轉接檔: .claude/skills/feature-design/SKILL.md", out)

    def test_unaliased_code_review_adapter_is_orphan_and_alias_missing(self):
        self._build_valid_tree()
        (self.root / ".claude/skills/gate2-code-review/SKILL.md").unlink()
        (self.root / ".claude/skills/gate2-code-review").rmdir()
        self._write(".claude/skills/code-review/SKILL.md", _skill_adapter("code-review", "code-review"))
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn(".claude/skills/gate2-code-review/SKILL.md", out)
        self.assertIn("孤兒 Skill 轉接檔（無對應正本）: .claude/skills/code-review", out)

    def test_description_drift_fails(self):
        self._build_valid_tree()
        self._write(".claude/skills/feature-design/SKILL.md",
                    _skill_adapter("feature-design", "feature-design", desc="outdated description"))
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("description 與正本不一致", out)

    def test_wrong_name_fails(self):
        self._build_valid_tree()
        self._write(".claude/skills/feature-design/SKILL.md", _skill_adapter("renamed", "feature-design"))
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("name 應為 'feature-design'", out)

    def test_adapter_exceeding_line_limit_fails(self):
        self._build_valid_tree()
        self._write(".claude/skills/feature-design/SKILL.md",
                    _skill_adapter("feature-design", "feature-design", extra_lines=self.mod.ADAPTER_MAX_LINES))
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("疑似複製正本內容", out)

    def test_missing_role_adapter_fails(self):
        self._build_valid_tree()
        self._write(".agents/architect/AGENT.md", "# Architect\n")
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("缺少 Claude Code 轉接檔: .claude/agents/architect.md", out)

    def test_role_adapter_without_source_pointer_fails(self):
        self._build_valid_tree()
        self._write(".claude/agents/gatekeeper.md", _role_adapter("gatekeeper", pointer=False))
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("未指向正本 .agents/gatekeeper/AGENT.md", out)

    def test_orphan_role_adapter_fails(self):
        self._build_valid_tree()
        self._write(".claude/agents/ghost.md", _role_adapter("ghost"))
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("孤兒角色轉接檔（無對應正本）: .claude/agents/ghost.md", out)

    def test_role_adapter_missing_description_fails(self):
        self._build_valid_tree()
        self._write(".claude/agents/gatekeeper.md",
                    "---\nname: gatekeeper\n---\n\n讀取 `.agents/gatekeeper/AGENT.md`。\n")
        ok, out = self._run()
        self.assertFalse(ok)
        self.assertIn("缺少 description", out)


if __name__ == "__main__":
    unittest.main()
