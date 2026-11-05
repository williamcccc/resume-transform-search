import argparse


def parse_cli_arguments():
    parser = argparse.ArgumentParser(
        description="文件與履歷智慧轉語意化 Markdown 工具 (支援 PDF、Word、智慧自動判別、自我審核修復、目錄批次處理)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
範例用法:
  # 1. 智慧自動判別 (自動處理 Word/PDF，遇 104 混淆字型自動走視覺 OCR，自動套用 .env 模型)
  python convert_to_md.py document.pdf
  python convert_to_md.py document.docx
  python convert_to_md.py resume.pdf custom_output.md

  # 2. 目錄批次轉檔 (自動轉換目錄下所有文件，可搭配 -r 遞迴搜尋子目錄與 --quarantine 隔離)
  python convert_to_md.py resume/BE -o output_md/
  python convert_to_md.py resume/ -o output_md/ -r --audit-report batch_audit.csv --quarantine quarantine/

  # 3. 啟用兩階段自我審核與修復機制 (Self-Refinement，排版最嚴密、零遺漏)
  python convert_to_md.py resume.pdf --review
  python convert_to_md.py resume.docx --review

  # 4. 強制指定模式
  python convert_to_md.py document.pdf --gemini   # 強制走 Gemini 多模態語意模式
  python convert_to_md.py document.pdf --ocr      # 強制走本機離線 RapidOCR
  python convert_to_md.py document.pdf --fast     # 強制走本機原生純文字提取

  # 5. 覆蓋 .env 模型設定
  python convert_to_md.py document.pdf --model gemini-3.8-flash
"""
    )

    parser.add_argument("input_pos", nargs="?", help="輸入檔案或目錄路徑 (支援 .pdf, .docx, .doc)")
    parser.add_argument("output_pos", nargs="?", help="輸出 Markdown 檔案或目錄路徑 (選填，若輸入為目錄則批次存入該目錄)")
    parser.add_argument("-i", "--input", dest="input_flag", help="輸入檔案或目錄路徑 (選項引數)")
    parser.add_argument("-o", "--output", dest="output_flag", help="輸出 Markdown 檔案或目錄路徑 (選項引數)")

    # 批次處理選項
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="批次轉檔時遞迴搜尋所有子目錄中的文件")

    # 自我審核修復選項
    parser.add_argument("--review", "--self-heal", dest="review", action="store_true",
                        help="啟用兩階段自我審核與自動修復機制 (Self-Refinement，透過 Chat 對照原圖二次校驗)")

    # 解析模式選項
    parser.add_argument("--gemini", action="store_true", help="強制啟用 Google Gemini 多模態語意結構化")
    parser.add_argument("--ocr", action="store_true", help="強制啟用本機 RapidOCR 純離線辨識")
    parser.add_argument("--fast", action="store_true", help="強制啟用本機原生快速文字提取")

    # Gemini 相關設定
    parser.add_argument("--api-key", help="指定 Gemini API Key (可選，預設讀取 .env 或環境變數)")
    parser.add_argument("--model", help="指定 Gemini 模型名稱 (可選，預設讀取 .env 或 gemini-3.8-flash)")

    # 品質品管與審計選項
    parser.add_argument("--quarantine", help="指定品質不合格時的隔離目錄 (例如: resume/quarantine)")
    parser.add_argument("--audit-report", help="指定批次品管報告 CSV 輸出路徑 (例如: audit_report.csv)")

    # 防線二：獨立客觀評判員 (LLM-as-a-Judge)
    parser.add_argument("--judge", "--llm-judge", dest="judge", action="store_true",
                        help="啟用防線二：獨立客觀評審員 (LLM-as-a-Judge) 輸出 JSON 評分卡")
    parser.add_argument("--save-scorecard", dest="save_scorecard",
                        help="指定評判員 JSON 評分卡儲存路徑或目錄 (例如: scorecard.json 或 scorecards/)")

    # 向量化與 Redis 檢索選項
    parser.add_argument("--index-to-redis", action="store_true",
                        help="轉檔成功後自動將 Markdown 履歷語意切片並向量化存入 Redis")
    parser.add_argument("--redis-url", help="指定 Redis 連線字串 (預設讀取 .env 或 redis://localhost:6379/0)")

    return parser, parser.parse_args()
