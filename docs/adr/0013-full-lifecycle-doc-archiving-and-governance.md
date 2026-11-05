# ADR-0013: 專案全生命週期文檔持久化體系與雙重歸檔架構

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
原先系統在執行 7 步驟閉環工作流時，Step 1（PRD 與 Tech Spec）與 Step 4（QA 實測報告）主要輸出於系統臨時 Artifacts 目錄，導致在一般檔案總管或 IDE 專案樹中無法直接查閱設計規格與驗收紀錄。需要建立專案持久化目錄架構並統一追溯中樞。

## 3. 評估選項 (Options Evaluated)
* **選項 A：僅保留對話臨時 Artifacts**：難以受 Git 版本控制，專案持久性不足。
* **選項 B：建立 `docs/specs/`、`docs/qa_reports/` 與 `docs/templates/` 專案持久化庫**：與 Artifacts 雙寫並存，兼顧即時 UI 展開與 Git 版控透明度。

## 4. 架構決策 (Decision Outcome)
採納選項 B。建立全景文檔體系中樞 `docs/README.md`，並更新 `AGENTS.md` / `GEMINI.md` 閉環規範與 `verify_doc_sync.py` 自動化檢驗。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私**：所有技術規格皆無未脫敏個資。
2. **容量與極限**：純文字 Markdown，佔用空間極小。
3. **可抽換性**：標準 Markdown，零廠商鎖定。
4. **成本**：0 Token 消耗。
5. **可觀測性**：建立 ADR ➔ Spec ➔ Code ➔ Tests ➔ QA Report 之 100% 雙向追溯鏈。
