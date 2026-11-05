# PRD 與 DDD 技術實作規格書 (ADR-0015 / 規格 0015)

## 一、產品需求文件 (PRD)

### 1. 商業背景與使用者目標 (Problem Statement & Goals)
目前系統在入庫完成後（已將 2,000+ 履歷語意切片與 768 維 Embedding 寫入 Redis HNSW 向量庫），使用者僅能透過命令列終端機 `search_resumes.py` 進行黑底白字的檢索，一般企業招募人員（HR / Recruiter）或用人主管在操作時存在以下痛點：
1. **缺乏視覺化圖形操作介面**：無法透過瀏覽器點選篩選器或直觀閱讀候選人經歷。
2. **缺乏制式硬性條件（如工作年資）複合過濾**：招募場景中，通常需要同時滿足「自然語言能力描述」（例如：分散式後端高並發架構）與「硬性門檻」（例如：工作經驗 3 年以上、具備特定技術標籤）。
3. **缺乏即時履歷全文閱讀彈窗**：檢索命中切片後，使用者需要手動去資料夾翻找 Markdown 檔案，無法一鍵預覽該求職者的完整履歷。

本功能旨在於既有 Web 儀表板架構中，擴充**「智能履歷語意與制式條件檢索中心」**，提供結合**「自然語言語意向量搜尋」**與**「結構化年資、技術標籤、區段類型」**的複合查詢 Web 介面。

### 2. 範疇界定 (Scope)
* **In-Scope**:
  1. **【自然語言語意檢索 (Natural Language Semantic Search)】**：
     - 輸入語句（如：「熟悉高並發分散式後端架構與微服務設計」）。
     - 調用 `GeminiEmbeddingService` 生成 768 維查詢向量，在 Redis 執行 HNSW KNN 向量檢索。
     - 提供快捷範例 Pills（「高並發後端」、「K8s 雲端架構」、「電商金流串接」、「SQA 自動化測試」、「前端 React/Vue」），點擊自動代入。
  2. **【制式結構化條件篩選 (Structured Filters)】**：
     - **最低工作年資 (Years of Experience)**：支援「不限」、「1年以上」、「3年以上」、「5年以上」、「8年以上」、「10年以上」。
     - **技術標籤 (Skills Tags)**：多選或以逗號分隔輸入（如 `python`, `docker`, `redis`），支援 RediSearch Tag 混合過濾。
     - **履歷區塊類型 (Chunk Section)**：全部、工作經歷 (Experience)、技能專長 (Skills)、專案作品 (Project)、個人簡介 (Profile)、學歷 (Education)。
     - **最低相似度門檻 (Min Score)**：0% ~ 100%（預設 50%）。
  3. **【候選人聚合與切片明細雙檢視 (View Modes)】**：
     - **依候選人整合視角 (Group by Candidate, 預設)**：整合該候選人最高相似度、提取之年資、擁有之技術標籤清單、匹配的經歷/技能切片折疊展開。
     - **切片明細視角 (All Chunks)**：單一切片條目呈現。
  4. **【履歷全文安全預覽 (Full Resume Modal Preview)】**：
     - 提供 API `GET /api/resume?candidate_id=...`，安全讀取本機來源 Markdown 檔案並回傳。
     - 網頁提供 Markdown 彈窗預覽，防止路徑遍歷（Path Traversal 隔離防禦）。
  5. **【雙引擎相容 (FastAPI & Builtin HTTPServer)】**：
     - 同時在 `FastAPI`（提供 `/docs` Swagger 文件）與內建 `ThreadingHTTPServer` 實作 API 端點，保證零依賴降級亦能順暢運行。
* **Out-of-Scope**:
  - 本階段不修改 Redis 原生向量 Schema（現有索引已包含 `skills`, `chunk_type`, `candidate_id`）。
  - 年資資訊由系統動態從履歷 Header 與 Experience 段落解析，不強制全庫重寫。

### 3. 輸入與輸出合約 (Input & Output Contract)
* **API: `POST /api/search` 或 `GET /api/search`**
  - 請求參數 (Query / Body):
    ```json
    {
      "query_text": "熟悉微服務架構與金流系統的資深後端",
      "min_years": 3,
      "skills": ["python", "redis"],
      "chunk_type": "experience",
      "min_score": 0.5,
      "top_k": 20,
      "group_by_candidate": true
    }
    ```
  - 回傳結果 JSON:
    ```json
    {
      "total_candidates": 5,
      "total_chunks": 12,
      "query": "熟悉微服務架構與金流系統的資深後端",
      "filters": {
        "min_years": 3,
        "skills": ["python", "redis"],
        "chunk_type": "experience",
        "min_score": 0.5
      },
      "candidates": [
        {
          "candidate_id": "王小明_BE",
          "candidate_name": "王小明",
          "years_of_experience": 4.5,
          "experience_raw": "4~5年工作經歷",
          "max_score": 0.824,
          "all_skills": ["python", "redis", "fastapi", "docker"],
          "matched_chunks": [
            {
              "chunk_id": "王小明_BE:3",
              "chunk_type": "experience",
              "section_title": "數位科技｜資深工程師",
              "score": 0.824,
              "content": "### 數位科技｜資深工程師...",
              "skills": ["python", "redis"]
            }
          ]
        }
      ]
    }
    ```
* **API: `GET /api/resume?candidate_id=王小明_BE`**
  - 回傳:
    ```json
    {
      "candidate_id": "王小明_BE",
      "candidate_name": "王小明",
      "file_path": "output_md/sample_resume.md",
      "markdown": "# 王小明\n- **工作經歷**：4~5年工作經歷..."
    }
    ```

### 4. 驗收標準 (Acceptance Criteria, AC)
* **AC-1 (Semantic Vector Search)**: 輸入自然語言查詢，能透過 Gemini Embedding 與 Redis HNSW 取得相關候選人，返回 Cosine 相似度與高亮內文。
* **AC-2 (Experience Years Filtering)**: 指定 `min_years = 3` 時，正確過濾年資未滿 3 年之候選人；若履歷記載 `4~5年`，其有效年資判定為 4 年並成功命中。
* **AC-3 (Skills & Chunk Type Tag Filtering)**: 指定技術標籤（如 `python, docker`）與區段（如 `experience`）時，能正確在 RediSearch 進行標籤交集過濾。
* **AC-4 (Candidate Aggregation & Modal Preview)**: 預設依求職者整合呈現，並能透過 `/api/resume` 取得完整 Markdown 履歷以彈窗預覽，防範路徑遍歷越權。
* **AC-5 (Web UI & Dual-Engine Sync)**: 在 Web 介面提供直觀搜尋列、年資選單、標籤選單與卡片展示；在 FastAPI 與 Builtin 雙引擎中皆實作並通過單元與 E2E 測試。

---

## 二、8 大架構維度前審 (Gate 1 審查)

1. **個資隱私 (PII)**：履歷預覽與檢索結果只對本機/授權內網開放，日誌中不記錄候選人個資。
2. **容量與極限 (Capacity)**：Redis 查詢結果透過 `top_k`（預設 20，上限 100）截斷，避免傳回巨量切片佔用 RAM。
3. **非同步與演進 (Async / Evolution)**：檢索 Use Case 保持純淨無狀態，Web 端支援非同步 ASGI。
4. **成本與熔斷 (Cost)**：僅在自然語言查詢時調用 1 次 Gemini Embedding API（Token 消耗極微，每次僅約 20~50 tokens）；制式過濾純由本地 Redis/Python 處理，0 額外 API 調用。
5. **可抽換性 (Portability)**：遵循 DIP，Use Case 依賴 `IVectorStore` 與 `IEmbeddingService`。
6. **輸入安全性 (Input Security)**：防範路徑遍歷攻擊（`candidate_id` 嚴格限制為合法檔名字元，禁止 `..` 或絕對路徑存取非授權目錄）。
7. **版本相容性 (Versioning)**：不修改現行 `idx:resumes:v1` Schema，向下相容 `search_resumes.py` CLI。
8. **可觀測性與追溯性 (Observability)**：記錄檢索耗時、命中切片總數與過濾後筆數。

---

## 三、DDD 技術實作規格書 (Tech Spec)

### 1. 模組規劃
```
src/
├── domain/
│   ├── models.py                     # CandidateSummary, SearchQuery (擴充 min_years)
│   └── interfaces.py                 # IExperienceExtractor (年資解析契約)
├── application/
│   ├── dto.py                        # WebSearchQueryDTO, WebSearchResultDTO
│   └── search_resumes_use_case.py   # 擴充 execute_grouped_with_filters, get_resume_markdown
├── infrastructure/
│   └── parsers/
│       └── experience_parser.py      # 正則年資解析器 (解析 "4~5年", "3年以上" 等)
└── interfaces/
    └── web/
        ├── fastapi_server.py         # 新增 /api/search 與 /api/resume 路由
        ├── server.py                 # 內建伺服器同步新增 /api/search 與 /api/resume
        └── static/
            └── dashboard.html        # 新增 Tab 3: 智能履歷搜尋 (含篩選器、候選人卡片與全文 Modal)
```

### 2. 測試計畫
- 單元測試：`tests/unit/test_resume_web_search.py`（Mock Embedding & VectorStore，驗證年資解析、條件篩選、候選人分組、全文路徑遍歷防禦）。
- E2E 測試：`tests/e2e/test_resume_web_search_e2e.py`（真實 API 端點實測、FastAPI Swagger `/docs` 整合）。

---

## 四、Gate 1 審查結論
8 大架構維度檢核通過，無破壞性變更，**Gate 1 審查通過 (PASS)**，放行進入 Step 2 實作。
