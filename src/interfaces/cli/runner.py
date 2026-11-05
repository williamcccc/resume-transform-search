import csv
import datetime
import json
import logging
import pathlib
import sys
import time
from typing import Optional, List, Tuple

from src.infrastructure.logging import setup_logging

from src.application.convert_document_use_case import ConvertDocumentUseCase
from src.application.dto import ConversionCommand
from src.domain.enums import ConversionMode
from src.infrastructure.config import AppConfig
from src.infrastructure.probes.pdf_probe import PdfHealthProbe
from src.infrastructure.readers.doc_word_reader import DocWordReader
from src.infrastructure.readers.docx_reader import DocxReader
from src.infrastructure.readers.pdf_renderer import PdfRenderer
from src.infrastructure.readers.pdf_text_reader import PdfTextReader
from src.infrastructure.transformers.fast_text_transformer import FastTextTransformer
from src.infrastructure.transformers.gemini_transformer import GeminiTransformer
from src.infrastructure.transformers.rapid_ocr_transformer import RapidOcrTransformer
from src.infrastructure.validators.quality_validator import MarkdownQualityValidator
from src.infrastructure.validators.llm_judge import GeminiLlmJudge
from src.interfaces.cli.args import parse_cli_arguments

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}
logger = logging.getLogger("cli.runner")


def build_use_case(config: AppConfig) -> ConvertDocumentUseCase:
    """工廠函式：組裝依賴項並建立 ConvertDocumentUseCase (包含品質檢核閥與獨立評審員)"""
    readers = [
        DocxReader(
            max_expansion_ratio=config.max_docx_expansion_ratio,
            max_uncompressed_bytes=config.max_docx_uncompressed_mb * 1024 * 1024,
        ),
        DocWordReader(),
        PdfTextReader(max_pages=config.max_pdf_pages),
    ]
    pdf_renderer = PdfRenderer(
        max_pages=config.max_pdf_pages,
        default_dpi=config.pdf_render_dpi,
    )
    pdf_probe = PdfHealthProbe(
        scanned_min_chars=config.pdf_scanned_min_chars,
        ufffd_threshold=config.pdf_obfuscated_ufffd_threshold,
        strikethrough_threshold=config.pdf_obfuscated_strikethrough_threshold,
    )

    gemini_transformer = (
        GeminiTransformer(
            api_key=config.gemini_api_key,
            model_name=config.gemini_model,
            temperature=config.gemini_temperature,
            max_output_tokens=config.gemini_max_output_tokens,
            vision_review_max_pages=config.vision_review_max_pages,
        )
        if config.gemini_api_key
        else None
    )
    llm_judge = (
        GeminiLlmJudge(api_key=config.gemini_api_key, model_name=config.gemini_model)
        if config.gemini_api_key
        else None
    )
    rapid_ocr = RapidOcrTransformer()
    fast_text = FastTextTransformer()
    quality_validator = MarkdownQualityValidator(
        pass_threshold=config.quality_threshold,
        min_retention_ratio=config.quality_min_retention_ratio,
        max_retention_ratio=config.quality_max_retention_ratio,
    )

    return ConvertDocumentUseCase(
        readers=readers,
        pdf_renderer=pdf_renderer,
        pdf_probe=pdf_probe,
        gemini_transformer=gemini_transformer,
        rapid_ocr_transformer=rapid_ocr,
        fast_transformer=fast_text,
        quality_validator=quality_validator,
        llm_judge=llm_judge,
        max_file_size_mb=config.max_file_size_mb,
        pdf_render_dpi=config.pdf_render_dpi,
        pdf_ocr_dpi=config.pdf_ocr_dpi,
        pdf_text_first_min_chars=config.pdf_text_first_min_chars,
    )



def append_audit_report(
    csv_path: pathlib.Path,
    filename: str,
    status: str,
    score: int,
    model: str,
    reviewed: bool,
    warnings: list,
    judge_score: Optional[int] = None,
):
    """追加一筆品管紀錄至 CSV 報告"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Filename", "Status", "Score", "JudgeScore", "Model", "Reviewed", "Warnings"])
        writer.writerow([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            status,
            score,
            judge_score if judge_score is not None else "N/A",
            model,
            reviewed,
            "; ".join(warnings) if warnings else "None"
        ])


def discover_documents(dir_path: pathlib.Path, recursive: bool = False) -> List[pathlib.Path]:
    """搜尋目錄下所有支援的文件檔案 (.pdf, .docx, .doc)，排除暫存檔與隱藏檔"""
    pattern = "**/*" if recursive else "*"
    files = [
        p for p in dir_path.glob(pattern)
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and not p.name.startswith("~$")
        and not p.name.startswith(".")
    ]
    return sorted(files, key=lambda x: str(x).lower())


def convert_single_file(
    file_path: pathlib.Path,
    target_output_path: pathlib.Path,
    use_case: ConvertDocumentUseCase,
    config: AppConfig,
    mode: ConversionMode,
    quarantine_dir: Optional[pathlib.Path] = None,
    audit_report_path: Optional[pathlib.Path] = None,
    prefix_tag: str = "",
    quota_already_exhausted: bool = False,
    save_scorecard_path: Optional[pathlib.Path] = None,
    index_to_redis: bool = False,
) -> Tuple[bool, bool, Optional[int], bool]:
    """
    執行單一文件轉換、品管檢驗、獨立評審與儲存輸出
    回傳值: (is_success, is_quarantined, score, is_quota_exhausted)
    """
    tag = f"{prefix_tag} " if prefix_tag else ""
    model_name = config.gemini_model if mode in (ConversionMode.AUTO, ConversionMode.GEMINI) else mode.value
    start_time = time.perf_counter()

    # 若已知當日配額已耗盡，直接快速標記至稽核報告，避免浪費時間進行無效呼叫
    if quota_already_exhausted:
        print(f"{tag}[配額略過] {file_path.name}: API 每日配額已耗盡，略過轉換並記錄至日誌")
        logger.warning("檔案處理略過 [%s] - 原因: API 每日配額已耗盡", file_path.name)
        if audit_report_path:
            append_audit_report(
                csv_path=audit_report_path,
                filename=file_path.name,
                status="RESOURCE_EXHAUSTED",
                score=0,
                model=model_name,
                reviewed=config.gemini_review,
                warnings=["429 RESOURCE_EXHAUSTED: Google API 每日配額已達上限，略過呼叫"],
                judge_score=None
            )
        return False, False, None, True

    print(f"{tag}[資訊] 正在處理: {file_path.name}")

    cmd = ConversionCommand(
        file_path=file_path,
        mode=mode,
        api_key=config.gemini_api_key,
        model_name=config.gemini_model,
        enable_review=config.gemini_review,
        enable_judge=config.gemini_judge
    )

    try:
        result = use_case.execute(cmd)
        if not result.success:
            print(f"{tag}[錯誤] 轉換失敗: {result.error_message}")
            file_elapsed = time.perf_counter() - start_time
            logger.error("檔案轉換失敗 [%s] - 耗時: %.3f 秒: %s", file_path.name, file_elapsed, result.error_message)
            if audit_report_path:
                append_audit_report(
                    csv_path=audit_report_path,
                    filename=file_path.name,
                    status="ERROR",
                    score=0,
                    model=model_name,
                    reviewed=config.gemini_review,
                    warnings=[f"轉換失敗: {result.error_message}"],
                    judge_score=None
                )
            return False, False, None, False

        actual_output_path = target_output_path
        is_quarantined = False
        score: Optional[int] = None
        status_tag = "PASS"
        all_warnings: List[str] = []

        # 防線一：確定性規則品管
        if result.quality_report:
            qr = result.quality_report
            score = qr.score
            status_tag = qr.summary_status
            all_warnings.extend(qr.warnings)

            print(f"{tag}[品管] 確定性評分: {qr.score}/100 [{status_tag}]")
            if qr.retention_ratio is not None:
                print(f"{tag}      篇幅保留率: {qr.retention_ratio:.1%}")

            if qr.warnings:
                for w in qr.warnings:
                    print(f"{tag}      [!] {w}")

        # 防線二：獨立客觀評審員 (LLM-as-a-Judge) JSON 評分卡
        judge_score: Optional[int] = None
        if result.judge_scorecard:
            js = result.judge_scorecard
            judge_score = js.overall_score
            print(f"{tag}[評判員] LLM 評審結論: {js.overall_score}/100 [{js.verdict}]")
            print(f"{tag}      完整度: {js.completeness_score} | 真實度: {js.fidelity_score} | 規範度: {js.structure_score}")
            if js.critique:
                print(f"{tag}      評語: {js.critique}")
            if js.missing_items:
                print(f"{tag}      [!] 評判遺漏項: {', '.join(js.missing_items)}")
                all_warnings.append(f"評判遺漏: {', '.join(js.missing_items)}")
            if js.hallucinations:
                print(f"{tag}      [!] 評判幻覺項: {', '.join(js.hallucinations)}")
                all_warnings.append(f"評判幻覺: {', '.join(js.hallucinations)}")

            # 儲存評分卡 JSON
            if save_scorecard_path:
                if (
                    save_scorecard_path.is_dir()
                    or save_scorecard_path.suffix.lower() != ".json"
                    or str(save_scorecard_path).endswith(("/", "\\"))
                ):
                    save_scorecard_path.mkdir(parents=True, exist_ok=True)
                    sc_file = save_scorecard_path / f"{file_path.stem}_scorecard.json"
                else:
                    sc_file = save_scorecard_path
                sc_file.parent.mkdir(parents=True, exist_ok=True)
                sc_content = js.raw_json or json.dumps(js.to_dict(), ensure_ascii=False, indent=2)
                sc_file.write_text(sc_content, encoding="utf-8")
                print(f"{tag}      評分卡已存至: {sc_file.resolve()}")

        # 防線三：隔離區機制判定 (規則評分 < 65 或 評判員裁決 FAIL)
        failed_rule = bool(result.quality_report and not result.quality_report.is_passed)
        failed_judge = bool(result.judge_scorecard and result.judge_scorecard.verdict == "FAIL")

        if (failed_rule or failed_judge) and quarantine_dir:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            actual_output_path = quarantine_dir / target_output_path.name
            is_quarantined = True
            reason = "評判員裁決 FAIL" if failed_judge else "規則評分未達標 (< 65)"
            print(f"{tag}[警告] 品質不合格 ({reason})，檔案已被移至隔離區: {actual_output_path.resolve()}")

        # 防線四：記錄審計報告
        if audit_report_path:
            append_audit_report(
                csv_path=audit_report_path,
                filename=file_path.name,
                status=status_tag if not failed_judge else "FAIL",
                score=score if score is not None else (judge_score or 0),
                model=result.model_used,
                reviewed=result.reviewed,
                warnings=all_warnings,
                judge_score=judge_score
            )

        # 寫入檔案
        actual_output_path.parent.mkdir(parents=True, exist_ok=True)
        actual_output_path.write_text(result.markdown, encoding="utf-8")

        if not is_quarantined:
            print(f"{tag}[成功] 轉換完成！檔案已儲存至: {actual_output_path.resolve()}")
            print(f"{tag}      模式: {result.model_used} | 健康度: {result.health.value} | 自我審核: {result.reviewed}")

            if index_to_redis:
                try:
                    from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker
                    from src.infrastructure.embeddings.gemini_embedding import GeminiEmbeddingService
                    from src.infrastructure.stores.redis_vector_store import RedisVectorStore
                    from src.application.index_resumes_use_case import IndexResumesUseCase
                    from src.application.dto import IndexCommand

                    chunker = MarkdownChunker(
                        min_chunk_chars=config.min_chunk_size,
                        max_chunk_chars=config.max_chunk_size,
                        extra_skill_patterns=config.extra_skill_patterns,
                    )
                    embedding_service = GeminiEmbeddingService(
                        api_key=config.gemini_api_key,
                        model_name=config.embedding_model,
                        dim=config.embedding_dim,
                        batch_size=config.embedding_batch_size,
                    )
                    vector_store = RedisVectorStore(
                        redis_url=config.redis_url,
                        index_name=config.redis_index_name,
                        prefix=config.redis_prefix,
                        hash_prefix=config.redis_hash_prefix,
                        hnsw_m=config.redis_hnsw_m,
                        hnsw_ef_construction=config.redis_hnsw_ef_construction,
                        hnsw_initial_cap=config.redis_hnsw_initial_cap,
                        distance_metric=config.redis_distance_metric,
                    )
                    idx_uc = IndexResumesUseCase(chunker, embedding_service, vector_store)
                    idx_res = idx_uc.execute(IndexCommand(file_path=actual_output_path))
                    print(f"{tag}      [Redis] 語意切片向量化成功，已存入 {idx_res.total_chunks} 個切片至 Redis")
                except Exception as ie:
                    print(f"{tag}[警告] Redis 向量化入庫失敗: {ie}")

        file_elapsed = time.perf_counter() - start_time
        logger.info(
            "檔案轉換完成 [%s] - 耗時: %.3f 秒, 狀態: %s, 確定性評分: %s, 評判員評分: %s",
            file_path.name,
            file_elapsed,
            "隔離" if is_quarantined else "成功",
            str(score),
            str(judge_score) if judge_score is not None else "N/A",
        )
        return True, is_quarantined, score or judge_score, False

    except Exception as e:
        err_str = str(e)
        err_lower = err_str.lower()
        is_quota = ("429" in err_str or "resource_exhausted" in err_lower or "quota" in err_lower)

        if is_quota:
            print(f"{tag}[配額耗盡] {file_path.name}: 429 RESOURCE_EXHAUSTED (每日 API 呼叫配額已滿)")
            if "requests per day" in err_lower or "free_tier_requests" in err_lower:
                warning_text = "429 RESOURCE_EXHAUSTED: Google API 每日配額已達上限 (Free Tier 20 RPD)，請更換模型或升級付費方案"
            else:
                warning_text = "429 RESOURCE_EXHAUSTED: API 呼叫配額耗盡，請更換模型或稍後重試"
            status = "RESOURCE_EXHAUSTED"
        else:
            print(f"{tag}[錯誤] 處理 {file_path.name} 時發生例外: {e}")
            warning_text = f"處理例外: {err_str[:120]}"
            status = "ERROR"

        file_elapsed = time.perf_counter() - start_time
        logger.error(
            "檔案處理異常 [%s] - 耗時: %.3f 秒, 狀態: %s: %s",
            file_path.name,
            file_elapsed,
            status,
            err_str[:120],
        )

        if audit_report_path:
            append_audit_report(
                csv_path=audit_report_path,
                filename=file_path.name,
                status=status,
                score=0,
                model=model_name,
                reviewed=config.gemini_review,
                warnings=[warning_text],
                judge_score=None
            )

        return False, False, None, is_quota


def run_cli() -> int:
    parser, args = parse_cli_arguments()

    input_path_str = args.input_flag or args.input_pos
    output_path_str = args.output_flag or args.output_pos

    # 決定模式
    if args.gemini:
        mode = ConversionMode.GEMINI
    elif args.ocr:
        mode = ConversionMode.OCR
    elif args.fast:
        mode = ConversionMode.FAST
    else:
        mode = ConversionMode.AUTO

    # 互動終端未提供輸入檔案時提示
    if not input_path_str:
        if sys.stdin and sys.stdin.isatty():
            try:
                input_path_str = input("請輸入檔案或目錄路徑 (.pdf / .docx / .doc): ").strip().strip('"\'')
                if not input_path_str:
                    print("[錯誤] 未提供輸入檔案或目錄。")
                    parser.print_help()
                    return 1
                if not output_path_str:
                    output_input = input("請輸入輸出 Markdown 檔案或目錄路徑 (直接按 Enter 則預設同名/同目錄): ").strip().strip('"\'')
                    if output_input:
                        output_path_str = output_input
            except (KeyboardInterrupt, EOFError):
                print("\n操作已取消。")
                return 0
        else:
            parser.print_help()
            return 1

    input_path = pathlib.Path(input_path_str)
    if not input_path.exists():
        print(f"[錯誤] 找不到輸入檔案或目錄: '{input_path}'")
        return 1

    # 載入設定
    config = AppConfig.load(
        override_api_key=args.api_key,
        override_model=args.model,
        override_review=args.review if args.review else None,
        override_judge=args.judge if args.judge else None,
        override_redis_url=getattr(args, "redis_url", None),
    )
    setup_logging(config)
    use_case = build_use_case(config)
    quarantine_str = args.quarantine or config.default_quarantine_dir
    quarantine_dir = pathlib.Path(quarantine_str) if quarantine_str else None

    audit_report_str = args.audit_report or config.default_audit_report
    audit_report_path = pathlib.Path(audit_report_str) if audit_report_str else None

    scorecard_str = args.save_scorecard or config.default_scorecard_dir
    save_scorecard_path = pathlib.Path(scorecard_str) if scorecard_str else None

    # -------------------------------------------------------------
    # 模式一：單一檔案轉換
    # -------------------------------------------------------------
    if input_path.is_file():
        if not output_path_str:
            output_path = input_path.with_suffix(".md")
        else:
            out_p = pathlib.Path(output_path_str)
            if out_p.is_dir() or output_path_str.endswith(("/", "\\")):
                output_path = out_p / (input_path.stem + ".md")
            else:
                output_path = out_p

        print(f"[資訊] 模型設定: {config.gemini_model} (自我審核: {'開啟' if config.gemini_review else '關閉'} | 獨立評判員: {'開啟' if config.gemini_judge else '關閉'})")
        success, quarantined, score, quota_hit = convert_single_file(
            file_path=input_path,
            target_output_path=output_path,
            use_case=use_case,
            config=config,
            mode=mode,
            quarantine_dir=quarantine_dir,
            audit_report_path=audit_report_path,
            save_scorecard_path=save_scorecard_path,
            index_to_redis=getattr(args, "index_to_redis", False),
        )
        return 0 if success else 1

    # -------------------------------------------------------------
    # 模式二：目錄批次轉換
    # -------------------------------------------------------------
    if input_path.is_dir():
        files = discover_documents(input_path, recursive=args.recursive)
        if not files:
            print(f"[警告] 在目錄 '{input_path}' 中找不到可處理的文件 (.pdf, .docx, .doc)")
            return 0

        active_output_str = output_path_str or config.default_output_dir
        output_dir = pathlib.Path(active_output_str) if active_output_str else None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 60)
        print("[資訊] 偵測到目錄輸入，啟動批次轉檔模式")
        print(f"[資訊] 來源目錄: {input_path.resolve()}")
        print(f"[資訊] 輸出目錄: {output_dir.resolve() if output_dir else '與各來源檔案同目錄'}")
        print(f"[資訊] 遞迴搜尋: {'開啟' if args.recursive else '關閉'}")
        print(f"[資訊] 找到文件數: {len(files)}")
        print(f"[資訊] 模型設定: {config.gemini_model} (自我審核: {'開啟' if config.gemini_review else '關閉'} | 獨立評判員: {'開啟' if config.gemini_judge else '關閉'})")
        if quarantine_dir:
            print(f"[資訊] 隔離目錄: {quarantine_dir.resolve()}")
        if audit_report_path:
            print(f"[資訊] 稽核報表: {audit_report_path.resolve()}")
        if save_scorecard_path:
            print(f"[資訊] 評分卡目錄: {save_scorecard_path.resolve()}")
        print("=" * 60)

        total_count = len(files)
        success_count = 0
        quarantine_count = 0
        failed_count = 0
        quota_exhausted_count = 0
        quota_already_exhausted = False
        scores: List[int] = []

        for idx, file_p in enumerate(files, 1):
            prefix = f"[{idx}/{total_count}]"
            print("-" * 60)

            if output_dir:
                if args.recursive:
                    try:
                        rel = file_p.relative_to(input_path)
                        target_file = (output_dir / rel).with_suffix(".md")
                    except ValueError:
                        target_file = (output_dir / file_p.name).with_suffix(".md")
                else:
                    target_file = (output_dir / file_p.name).with_suffix(".md")
            else:
                target_file = file_p.with_suffix(".md")

            item_quarantine = quarantine_dir
            if quarantine_dir and args.recursive:
                try:
                    rel = file_p.relative_to(input_path)
                    item_quarantine = quarantine_dir / rel.parent
                except ValueError:
                    item_quarantine = quarantine_dir

            # 若批次指定儲存評分卡
            item_scorecard = None
            if save_scorecard_path:
                if save_scorecard_path.is_dir() or args.recursive or not str(save_scorecard_path).endswith(".json"):
                    save_scorecard_path.mkdir(parents=True, exist_ok=True)
                    if args.recursive:
                        try:
                            rel = file_p.relative_to(input_path)
                            item_scorecard = (save_scorecard_path / rel.parent / f"{file_p.stem}_scorecard.json")
                        except ValueError:
                            item_scorecard = save_scorecard_path / f"{file_p.stem}_scorecard.json"
                    else:
                        item_scorecard = save_scorecard_path / f"{file_p.stem}_scorecard.json"
                else:
                    item_scorecard = save_scorecard_path

            succ, quar, sc, quota_hit = convert_single_file(
                file_path=file_p,
                target_output_path=target_file,
                use_case=use_case,
                config=config,
                mode=mode,
                quarantine_dir=item_quarantine,
                audit_report_path=audit_report_path,
                prefix_tag=prefix,
                quota_already_exhausted=quota_already_exhausted,
                save_scorecard_path=item_scorecard,
                index_to_redis=getattr(args, "index_to_redis", False),
            )

            if succ:
                success_count += 1
            else:
                failed_count += 1

            if quar:
                quarantine_count += 1

            if quota_hit:
                quota_exhausted_count += 1
                quota_already_exhausted = True

            if sc is not None:
                scores.append(sc)

        avg_score = (sum(scores) / len(scores)) if scores else 0.0
        print("\n" + "=" * 60)
        print("【批次轉檔彙總報表】")
        print(f"- 總處理檔案數: {total_count}")
        print(f"- 轉換成功檔案: {success_count}")
        print(f"- 隔離檔案 (<65分): {quarantine_count}")
        if quota_exhausted_count > 0:
            print(f"- 轉換失敗檔案: {failed_count} (其中 {quota_exhausted_count} 筆因 429 配額耗盡)")
        else:
            print(f"- 轉換失敗檔案: {failed_count}")
        print(f"- 平均品質得分: {avg_score:.1f} 分")
        if audit_report_path:
            print(f"- 批量稽核日誌: {audit_report_path.resolve()}")
        if quota_exhausted_count > 0:
            print("\n[!] 提示：偵測到 429 RESOURCE_EXHAUSTED，未處理檔案已全數標記於稽核日誌。")
            print("    建議處理方式：")
            print("    1. 切換高配額模型：--model gemini-2.0-flash (每日 1,500 次免費額度)")
            print("    2. 切換本機離線模式：--fast (健康檔案快速提取) 或 --ocr (本機光學辨識)")
            print("    3. 升級至 Google AI Studio Pay-as-you-go 計費方案解鎖限額")
        print("=" * 60)

        return 0 if failed_count == 0 else 1
