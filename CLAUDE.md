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
3. **Skill 路徑**：閉環各階段之 Skill 位於 `.agents/skills/<skill>/SKILL.md`（非 Claude Code 內建 Skill），階段開始前以 Read 讀取後依其指示執行。
