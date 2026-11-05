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

