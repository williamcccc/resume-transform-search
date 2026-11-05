import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from src.infrastructure.config import AppConfig


_LOGGING_INITIALIZED = False


def setup_logging(
    config: Optional[AppConfig] = None,
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_max_bytes: Optional[int] = None,
    log_backup_count: Optional[int] = None,
    force_reinit: bool = False,
) -> logging.Logger:
    """
    初始化專案集中式系統技術日誌 (Infrastructure Logging)
    - 支援 RotatingFileHandler 滾動輪轉日誌檔 (預設 logs/app.log)
    - 支援 delay=True 與 UTF-8 編碼 (防止 Windows 檔案鎖死 WinError 32)
    - 支援 Twelve-Factor 環境變數與 AppConfig 注入覆寫
    """
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED and not force_reinit:
        return logging.getLogger("resume_agent")

    level_str = log_level or (config.log_level if config else "INFO")
    numeric_level = getattr(logging, level_str.upper(), logging.INFO)

    file_path_str = log_file if log_file is not None else (config.log_file if config else "logs/app.log")
    max_bytes = log_max_bytes or (config.log_max_bytes if config else 10 * 1024 * 1024)
    backup_count = log_backup_count or (config.log_backup_count if config else 5)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 移除舊有由本模組加入的 FileHandler，避免重複綁定
    for h in list(root_logger.handlers):
        if isinstance(h, RotatingFileHandler) and getattr(h, "_is_app_logger", False):
            root_logger.removeHandler(h)
            h.close()

    # 綁定滾動檔案日誌 (RotatingFileHandler)
    if file_path_str:
        log_path = Path(file_path_str)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler._is_app_logger = True
        root_logger.addHandler(file_handler)

    _LOGGING_INITIALIZED = True
    app_logger = logging.getLogger("resume_agent")
    app_logger.info(
        "系統技術日誌初始化完成 [等級: %s, 檔案: %s, 輪轉上限: %.1f MB, 保留份數: %d]",
        level_str.upper(),
        file_path_str or "無 (僅Console)",
        max_bytes / (1024 * 1024),
        backup_count,
    )
    return app_logger


def close_logging() -> None:
    """關閉並釋放所有由 setup_logging 建立的日誌 Handler (防止 Windows 檔案控制代碼鎖定)"""
    global _LOGGING_INITIALIZED
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        if getattr(h, "_is_app_logger", False):
            try:
                h.flush()
                h.close()
            except (OSError, ValueError):
                continue
            root_logger.removeHandler(h)
    _LOGGING_INITIALIZED = False


def get_logger(name: str) -> logging.Logger:
    """取得具備標準命名的模組 Logger"""
    return logging.getLogger(name)
