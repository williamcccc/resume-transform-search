from enum import Enum


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    UNKNOWN = "unknown"


class DocumentHealth(str, Enum):
    HEALTHY = "HEALTHY"          # 健康純文字
    SCANNED = "SCANNED"          # 純掃描圖檔 (缺乏文字層)
    OBFUSCATED = "OBFUSCATED"    # 104 防爬混淆字型 (大量亂碼或替換字)


class ConversionMode(str, Enum):
    AUTO = "auto"      # 智慧自動分流
    GEMINI = "gemini"  # 強制 Gemini 模式
    OCR = "ocr"        # 強制本機 RapidOCR 模式
    FAST = "fast"      # 強制原生快速文字模式


class ChunkType(str, Enum):
    PROFILE = "profile"           # 個人基本資料與自傳總結
    EXPERIENCE = "experience"     # 單一工作經歷 / 職務歷程
    SKILLS = "skills"             # 專業技能清單
    EDUCATION = "education"       # 學歷背景
    PROJECT = "project"           # 專案成就
    OTHER = "other"               # 其他一般段落
