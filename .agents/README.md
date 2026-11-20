# `.agents/` 目錄導覽

本目錄存放跨工具共用的閉環規範正本。最高準則與分流規則見 [AGENTS.md](../AGENTS.md)；本檔只說明目錄分工，不重複規則內容。

| 目錄 | 內容 | 回答的問題 |
| :--- | :--- | :--- |
| [workflows/](workflows/) | 流程檔：[feature.md](workflows/feature.md)、[bug.md](workflows/bug.md)、[hotfix.md](workflows/hotfix.md)、[governance.md](workflows/governance.md) | 何時做、先後順序、要不要做、失敗退回哪裡 |
| [skills/](skills/) | 各步驟技能與其範本、檢核清單、腳本 | 怎麼做、用什麼範本、通過標準 |
| [architect/](architect/AGENT.md)、[developer/](developer/AGENT.md)、[gatekeeper/](gatekeeper/AGENT.md) | 角色手冊：負責步驟、綁定技能、交接合約 | 誰做、交給誰 |
| [project.toml](project.toml)、[lib/](lib/project_config.py) | 專案專屬值的唯一正本與其讀取模組 | 閘門腳本檢查哪些路徑、清單與門檻 |
| [PORTING.md](PORTING.md) | 移植指南 | 搬到其他專案時要改什麼 |

**使用方式**：
1. 依 AGENTS.md 第 2 節分流表判定軌別，讀取對應流程檔。
2. 每個步驟開始前讀取該步驟角色的 `AGENT.md`，並依流程檔指定的技能執行。
3. 預設由同一個助理依階段切換角色；只有使用者明確要求多代理協作時才派子 Agent（各工具的派工方式見 [CLAUDE.md](../CLAUDE.md)、[GEMINI.md](../GEMINI.md)）。

**修改本目錄**：一律走 [governance.md](workflows/governance.md)。只改正本，再同步 `.claude/` 轉接層與 `docs/templates/` 鏡像，並執行 `verify_doc_sync.py`。
