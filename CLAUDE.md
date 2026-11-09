# Claude Code 專屬規範 (Claude Code Overlay)

本專案之最高準則（架構紅線、雙門禁 7 步驟閉環、多 Agent Token 能效守則、編程與交付規範）統一記載於 [AGENTS.md](AGENTS.md)，以下匯入為唯一正本，**嚴禁於本檔複製其內容**：

@AGENTS.md

---

## Claude Code 專屬覆寫 (Tool-Specific Overrides)

僅記載 Claude Code 與 [AGENTS.md](AGENTS.md) 通用描述之對應差異；若有衝突，以 AGENTS.md 之紅線為準。

1. **Subagent 模型分級 (Model Tiering)**：角色轉接檔 frontmatter 之 `model` 為該角色預設值，派工時依任務性質以 Agent 工具之 `model` 參數覆寫（覆寫優先於 frontmatter）。

   | 任務 | 角色 | `model` |
   | :--- | :--- | :--- |
   | Step 1 需求規格化與 Gate 1 架構前審 | architect | `opus`（預設） |
   | Step 7 文檔與 ADR 同步 | architect | 覆寫 `sonnet` |
   | Step 2 實作、Step 3 單元測試、Step 6 一般修正 | developer | `sonnet`（預設） |
   | Step 6 深度 RCA（根因不明、跨層缺陷、第 3 輪修正） | developer | 覆寫 `opus` |
   | Step 5 Gate 2 對抗式代碼審查（含差異複審） | gatekeeper | `opus`（預設） |
   | Step 4 QA 實測（撰寫 E2E、邊界對抗、產出報告） | gatekeeper | 覆寫 `sonnet` |
   | 純機械化：跑測試、清理測試資料、執行 `verify_doc_sync.py` / `audit_guardrails.py`、檔案清單掃描 | 不指定角色 | `haiku` |

2. **派工一律新開子 Agent，嚴禁接續長上下文 (Fresh Agent per Dispatch)**：
   - Step 6 每一輪修正、Gate 2 每一次（含差異複審）、Step 7 文檔同步，**一律以 Agent 工具新派工**，嚴禁以 SendMessage 接續先前已完成任務之子 Agent；接續會使其攜帶全部歷史（數十次工具呼叫、全部讀檔與測試輸出），成本隨輪次累積而與實際工作量無關。
   - 新派工之 Prompt 僅含 Context Handoff Schema JSON：`artifacts`（規格/報告之專案相對路徑，並註明「僅讀第 X 節」）、缺陷清單（檔案:行號、重現方式）、`constraints`、驗證指令；嚴禁要求整份重讀大型規格或報告。
   - SendMessage 僅限用於**仍在執行中**之子 Agent 補充其當下任務所需之事實（如環境資訊），不得用於派發新階段或新一輪任務。
3. **報告雙寫 (Dual-Persistence)**：超過 30 行之 PRD、Tech Spec、QA 報告寫入 `docs/specs/`、`docs/qa_reports/` 之獨立 Markdown 檔案；需分享檢視時再以 Artifact 發布。
4. **Skill 路徑與原生探索**：閉環各階段 Skill 之正本位於 `.agents/skills/<skill>/SKILL.md`；`.claude/skills/<skill>/SKILL.md` 僅為 Claude Code 原生探索之轉接層（僅含 frontmatter 與一行讀取指示），可經 Skill 工具或 `/<skill>` 呼叫，載入後仍以 Read 讀取正本並依其指示執行。
   - 新增或修改 Skill 時只改正本；若變更 `name`/`description` 或新增 Skill，須同步更新對應轉接檔。
   - 專案之 `code-review` 技能於 Claude Code 中命名為 `gate2-code-review`，以避免與 Claude Code 內建 `/code-review` 指令衝突。
5. **角色子 Agent 轉接層**：`.claude/agents/<role>.md` 僅含 frontmatter（`name`、`description`、`model`）與讀取 `.agents/<role>/AGENT.md` 之指示，**僅於使用者明確要求多代理協作時派工**；子 Agent 已自動載入 AGENTS.md，轉接檔嚴禁指示重複讀取。`model` 須與第 1 項分級表之角色預設值一致。
