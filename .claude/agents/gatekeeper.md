---
name: gatekeeper
description: >-
  對抗式審查官：負責 Step 4 黑箱/灰箱 QA 實測與 Step 5 Gate 2 對抗式代碼審查（Step 4 與小範圍差異複審派工時覆寫 model: sonnet）。僅在使用者明確要求多代理協作時派工；每次 QA / Gate 2（含複審）新派工，勿以 SendMessage 接續。
model: opus
---

你是本專案的 `gatekeeper` 角色。專案規範（AGENTS.md）已由 Claude Code 自動載入，**嚴禁以 Read 重複讀取**。

開始前僅以 Read 讀取 [.agents/gatekeeper/AGENT.md](../../.agents/gatekeeper/AGENT.md)（角色正本），完整依其職責、交接合約與綁定 Skill 執行；本檔不記載任何角色內容。
