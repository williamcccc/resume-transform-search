from pydantic import BaseModel
from typing import Optional


class WebConversionResponse(BaseModel):
    """Web API 轉換成功回應模型"""
    success: bool
    filename: str
    markdown: str
    doc_type: str
    health_status: str
    model_used: str
    reviewed: bool
    char_count: int


class WebErrorResponse(BaseModel):
    """Web API 錯誤回應模型"""
    success: bool
    error: str
