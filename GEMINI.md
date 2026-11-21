# Google Antigravity 專屬規範 (Antigravity Overlay)

本專案之最高準則（架構紅線、雙門禁 7 步驟閉環、多 Agent Token 能效守則、編程與交付規範）統一記載於 [AGENTS.md](AGENTS.md)，以下匯入為唯一正本，**嚴禁於本檔複製其內容**：

@AGENTS.md

---

## Antigravity 專屬覆寫 (Tool-Specific Overrides)

僅記載 Antigravity 與 [AGENTS.md](AGENTS.md) 通用描述之對應差異；若有衝突，以 AGENTS.md 之紅線為準。

1. **Subagent 模型分級 (Model Tiering)**：調用 `invoke_subagent` 時明確指定模型。
   - 機械化探索、檔案清單掃描、語法檢查、測試執行：強制指定 `Model: 'flash'`。
   - Gate 1 架構前審、Gate 2 對抗式代碼審查、深度 RCA：始得調用 `Model: 'inherit'` 或 `'pro'`。
2. **Artifact-First**：超過 30 行之報告優先寫入 Artifact Markdown 檔案（供 UI 快速展開檢視），並依 AGENTS.md 同步持久化至 `docs/specs/`、`docs/qa_reports/`。
3. **需求澄清提問 (feature-design 階段 1.5)**：主對話於對話中以編號選擇題呈現澄清問題（含子 Agent 回報之問題），建議選項置首並標示「（建議）」。規則正本見 [requirement_clarification.md](.agents/skills/feature-design/references/requirement_clarification.md)。
4. **子 Agent 路徑傳遞**：傳送目標檔案時使用專案相對路徑；若工具必須使用絕對路徑，僅於執行期動態解析，嚴禁寫入任何版控檔案。
