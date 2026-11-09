# Claude Code 專屬規範 (Claude Code Overlay)

本專案之最高準則（架構紅線、雙門禁 7 步驟閉環、多 Agent Token 能效守則、編程與交付規範）統一記載於 [AGENTS.md](AGENTS.md)，以下匯入為唯一正本，**嚴禁於本檔複製其內容**：

@AGENTS.md

---

## Claude Code 專屬覆寫 (Tool-Specific Overrides)

僅記載 Claude Code 與 [AGENTS.md](AGENTS.md) 通用描述之對應差異；若有衝突，以 AGENTS.md 之紅線為準。

1. **Subagent 模型分級 (Model Tiering)**：透過 Agent 工具之 `model` 參數指定。
   - 機械化探索、檔案清單掃描、語法檢查、測試執行：`haiku`。
   - Gate 1 架構前審、Gate 2 對抗式代碼審查、深度 RCA：沿用主對話模型（Opus）或指定 `opus`。
2. **報告雙寫 (Dual-Persistence)**：超過 30 行之 PRD、Tech Spec、QA 報告寫入 `docs/specs/`、`docs/qa_reports/` 之獨立 Markdown 檔案；需分享檢視時再以 Artifact 發布。
3. **Skill 路徑與原生探索**：閉環各階段 Skill 之正本位於 `.agents/skills/<skill>/SKILL.md`；`.claude/skills/<skill>/SKILL.md` 僅為 Claude Code 原生探索之轉接層（僅含 frontmatter 與一行讀取指示），可經 Skill 工具或 `/<skill>` 呼叫，載入後仍以 Read 讀取正本並依其指示執行。
   - 新增或修改 Skill 時只改正本；若變更 `name`/`description` 或新增 Skill，須同步更新對應轉接檔。
   - 專案之 `code-review` 技能於 Claude Code 中命名為 `gate2-code-review`，以避免與 Claude Code 內建 `/code-review` 指令衝突。
4. **角色子 Agent 轉接層**：`.claude/agents/<role>.md` 僅含 frontmatter（`name`、`description`、`model`）與讀取 `.agents/<role>/AGENT.md` 之指示，**僅於使用者明確要求多代理協作時派工**；子 Agent 已自動載入 AGENTS.md，轉接檔嚴禁指示重複讀取。
