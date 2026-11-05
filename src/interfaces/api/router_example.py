"""
【Web API 路由轉接器範例 (FastAPI)】
展示如何無縫將 ConvertDocumentUseCase 接入 Web API。
此模組為架構展示與未來整合範本，核心業務邏輯零修改。
"""
from src.application.convert_document_use_case import ConvertDocumentUseCase
from src.application.dto import ConversionCommand
from src.domain.enums import ConversionMode
from src.infrastructure.config import AppConfig
from src.interfaces.api.dto import WebConversionResponse
from src.interfaces.cli.runner import build_use_case


async def convert_file_api_handler(
    filename: str,
    file_bytes: bytes,
    enable_review: bool = False,
    api_key: str = None
) -> WebConversionResponse:
    """
    Web API 處理器：直接接收記憶體檔案 bytes，不產生本機暫存檔！
    """
    config = AppConfig.load(override_api_key=api_key, override_review=enable_review)
    use_case: ConvertDocumentUseCase = build_use_case(config)

    command = ConversionCommand(
        file_bytes=file_bytes,
        filename=filename,
        mode=ConversionMode.AUTO,
        api_key=config.gemini_api_key,
        model_name=config.gemini_model,
        enable_review=config.gemini_review
    )

    result = use_case.execute(command)

    return WebConversionResponse(
        success=result.success,
        filename=filename,
        markdown=result.markdown,
        doc_type=result.doc_type.value,
        health_status=result.health.value,
        model_used=result.model_used,
        reviewed=result.reviewed,
        char_count=len(result.markdown)
    )
