class DomainError(Exception):
    """領域層基礎例外"""
    pass


class DocumentNotFoundError(DomainError):
    """找不到指定文件"""
    pass


class UnsupportedDocumentTypeError(DomainError):
    """不支援的文件格式"""
    pass


class ConversionError(DomainError):
    """文件轉換失敗"""
    pass


class FileQuotaExceededError(DomainError):
    """資源配額超限 (檔案過大、PDF 頁數過多或解壓膨脹比過高)"""
    pass



# ==========================================
# 招募助手 (ADR-0019) 領域例外
# ==========================================

class ChatUnavailableError(DomainError):
    """招募助手服務不可用 (無 API Key、未安裝 LangGraph、向量庫或 Checkpointer 不可用)"""
    pass


class LlmQuotaExhaustedError(DomainError):
    """LLM 配額用罄 (429) 經重試仍失敗，熔斷冷卻中"""

    def __init__(self, message: str, retry_after_seconds: int = 0):
        super().__init__(message)
        self.retry_after_seconds = int(retry_after_seconds)


class RecruitmentLlmError(DomainError):
    """招募助手 LLM 呼叫失敗 (非配額類錯誤，可由呼叫端平滑降級)"""
    pass


class LlmOutputTruncatedError(RecruitmentLlmError):
    """LLM 長文輸出被截斷（finish_reason=MAX_TOKENS、結構化解析失敗或括號不成對），呼叫端降級為模板"""
    pass


class SessionBusyError(DomainError):
    """同一 Session 上一輪尚未完成"""
    pass


class SessionTurnLimitError(DomainError):
    """Session 總輪數超過上限"""
    pass


class TurnTimeoutError(DomainError):
    """單輪處理超過逾時上限"""
    pass


class RecruitmentInputError(DomainError):
    """招募助手輸入驗證失敗 (error_code: INVALID_INPUT / MESSAGE_TOO_LONG)"""

    def __init__(self, message: str, error_code: str = "INVALID_INPUT"):
        super().__init__(message)
        self.error_code = error_code


class RelaxationDecisionError(DomainError):
    """放寬條件決定不合法 (error_code: INVALID_RELAXATION_DECISION / NO_PENDING_DECISION)，ADR-0022"""

    def __init__(self, message: str, error_code: str = "INVALID_RELAXATION_DECISION"):
        super().__init__(message)
        self.error_code = error_code
