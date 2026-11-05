import re
from typing import List, Optional, Set
from src.domain.enums import ChunkType
from src.domain.interfaces import IMarkdownChunker
from src.domain.models import ResumeChunk

# 常見技術與專業技能標籤庫 (用於自動標籤化與 Redis Tag Filter)
COMMON_SKILL_PATTERNS = [
    r"\bpython\b", r"\bgolang\b", r"\bgo\b", r"\bjava\b", r"\bc\+\+\b", r"\bc#\b", r"\b\.net\b",
    r"\bfastapi\b", r"\bdjango\b", r"\bflask\b", r"\bspring\s?boot\b", r"\bnodejs\b", r"\bnode\.js\b",
    r"\breact\b", r"\bvue\b", r"\bangular\b", r"\btypescript\b", r"\bjavascript\b",
    r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b", r"\bterraform\b", r"\bansible\b",
    r"\bredis\b", r"\bpostgresql\b", r"\bpostgres\b", r"\bmysql\b", r"\bmongodb\b", r"\belasticsearch\b",
    r"\bkafka\b", r"\brabbitmq\b", r"\bgrpc\b", r"\bgraphql\b", r"\brestful\b",
    r"\baws\b", r"\bgcp\b", r"\bazure\b", r"\blinux\b", r"\bgit\b", r"\bci/cd\b",
    r"\bpytorch\b", r"\btensorflow\b", r"\bllm\b", r"\brag\b", r"\blangchain\b"
]


class MarkdownChunker(IMarkdownChunker):
    """
    依據 Markdown 標題階層進行語意切片的實作
    - 確保工作經歷、學歷、技能各自獨立，避免跨公司內容被硬性切斷
    - 自動提取候選人姓名、任職公司、職稱與技能標籤
    - 支援過短切片智慧合併 (Chunk Merging)，提升向量語意密度並減少 Token 浪費
    """

    def __init__(
        self,
        min_chunk_chars: int = 80,
        max_chunk_chars: int = 1500,
        extra_skill_patterns: Optional[List[str]] = None,
    ):
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self.skill_patterns = list(COMMON_SKILL_PATTERNS)
        if extra_skill_patterns:
            for p in extra_skill_patterns:
                cleaned = p.strip()
                if not cleaned:
                    continue
                if not cleaned.startswith(r"\b") and not cleaned.startswith("^"):
                    pattern = rf"\b{re.escape(cleaned)}\b"
                else:
                    pattern = cleaned
                if pattern not in self.skill_patterns:
                    self.skill_patterns.append(pattern)

    def chunk_markdown(self, markdown: str, candidate_id: str, file_path: Optional[str] = None) -> List[ResumeChunk]:
        if not markdown or not markdown.strip():
            return []

        # 1. 提取求職者姓名 (由首個 # 標題提取)
        name_match = re.search(r"^#\s+([^\n#]+)", markdown, re.MULTILINE)
        candidate_name = name_match.group(1).strip() if name_match else candidate_id

        # 2. 依據標題切割段落
        lines = markdown.splitlines()
        chunks: List[ResumeChunk] = []

        current_h2_title = "基本資料"
        current_h2_type = ChunkType.PROFILE
        current_h3_title = ""
        current_buffer: List[str] = []
        chunk_idx = 0

        def classify_section(title: str) -> ChunkType:
            t_lower = title.lower()
            if any(k in t_lower for k in ["經歷", "工作", "experience", "職歷"]):
                return ChunkType.EXPERIENCE
            elif any(k in t_lower for k in ["技能", "專長", "skill", "技術"]):
                return ChunkType.SKILLS
            elif any(k in t_lower for k in ["學歷", "教育", "education", "畢業"]):
                return ChunkType.EDUCATION
            elif any(k in t_lower for k in ["專案", "成就", "project", "作品"]):
                return ChunkType.PROJECT
            elif any(k in t_lower for k in ["個人", "基本", "自傳", "profile", "about", "聯絡"]):
                return ChunkType.PROFILE
            return ChunkType.OTHER

        def parse_company_and_title(text: str) -> tuple[Optional[str], Optional[str]]:
            # 常見標題格式: "### 科技公司｜後端工程師" 或 "### 公司名稱 - 職稱"
            cleaned = re.sub(r"^#+\s*", "", text).strip()
            for sep in ["｜", "|", " - ", "—", "/"]:
                if sep in cleaned:
                    parts = cleaned.split(sep, 1)
                    return parts[0].strip(), parts[1].strip()
            return cleaned, None

        def extract_skills(text: str) -> List[str]:
            found: Set[str] = set()
            t_lower = text.lower()
            for pattern in self.skill_patterns:
                if re.search(pattern, t_lower):
                    # 正規化名稱
                    raw_matched = re.search(pattern, t_lower).group(0).strip()
                    if raw_matched in ("node.js", "nodejs"):
                        found.add("nodejs")
                    elif raw_matched in ("postgres", "postgresql"):
                        found.add("postgresql")
                    elif raw_matched in ("k8s", "kubernetes"):
                        found.add("kubernetes")
                    elif raw_matched in ("spring boot", "springboot"):
                        found.add("springboot")
                    else:
                        found.add(raw_matched)
            return sorted(list(found))

        def flush_chunk():
            nonlocal chunk_idx, current_buffer
            text = "\n".join(current_buffer).strip()
            if not text:
                current_buffer = []
                return

            # 若該區塊只包含二級標題而無實際內文 (例如 "## 工作經歷" 後緊接 "### 某某公司")，跳過此過渡標題
            body_only = re.sub(r"^#+\s*.*$", "", text, flags=re.MULTILINE).strip()
            if not body_only and not current_h3_title:
                current_buffer = []
                return

            raw_sec_title = current_h3_title if current_h3_title else current_h2_title
            sec_title = re.sub(r"^#+\s*", "", raw_sec_title).strip()
            c_type = current_h2_type
            company, job_title = None, None

            if current_h3_title:
                company, job_title = parse_company_and_title(current_h3_title)

            chunk_id = f"{candidate_id}:{chunk_idx}"
            chunk_idx += 1

            chunk_skills = extract_skills(text)
            chunks.append(ResumeChunk(
                chunk_id=chunk_id,
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                chunk_type=c_type,
                section_title=sec_title,
                content=text,
                skills=chunk_skills,
                company=company,
                job_title=job_title,
                file_path=file_path
            ))
            current_buffer = []

        # 遍歷各行進行切分
        for line in lines:
            if line.startswith("## "):
                # 遇到新的二級標題，結算前一個區塊
                flush_chunk()
                current_h2_title = line.strip()
                current_h2_type = classify_section(current_h2_title)
                current_h3_title = ""
                current_buffer.append(line)

            elif line.startswith("### "):
                # 遇到三級標題 (多半為各別經歷/專案)
                flush_chunk()
                current_h3_title = line.strip()
                current_buffer.append(line)

            else:
                current_buffer.append(line)

        flush_chunk()

        # 若沒有成功切分出任何 chunk (例如純文字無標題)，將整體視為一個 PROFILE chunk
        if not chunks and markdown.strip():
            chunks.append(ResumeChunk(
                chunk_id=f"{candidate_id}:0",
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                chunk_type=ChunkType.PROFILE,
                section_title="全文內容",
                content=markdown.strip(),
                skills=extract_skills(markdown),
                file_path=file_path
            ))

        return self._merge_small_chunks(chunks, candidate_id)

    def _merge_small_chunks(self, chunks: List[ResumeChunk], candidate_id: str) -> List[ResumeChunk]:
        """將過短切片智慧合併至鄰近區塊，提升語意完整度並降低向量化消耗"""
        if not chunks or len(chunks) <= 1:
            return chunks

        merged: List[ResumeChunk] = []
        for chunk in chunks:
            if not merged:
                merged.append(chunk)
                continue

            prev = merged[-1]
            prev_len = len(prev.content.strip())
            curr_len = len(chunk.content.strip())

            # 跨領域大類保護：若兩者皆為明確的獨立核心業務大類且類型不同 (如 SKILLS 與 EDUCATION)，不可跨類別合併
            is_same_or_compatible = (
                prev.chunk_type == chunk.chunk_type
                or prev.chunk_type in (ChunkType.OTHER, ChunkType.PROFILE)
                or chunk.chunk_type in (ChunkType.OTHER, ChunkType.PROFILE)
            )

            # 若符合相容性，且前一個或當前切片過短，且合併後字數未超過上限，則進行合併
            if is_same_or_compatible and (prev_len < self.min_chunk_chars or curr_len < self.min_chunk_chars) and (prev_len + curr_len <= self.max_chunk_chars):
                prev.content = f"{prev.content.rstrip()}\n\n{chunk.content.lstrip()}"
                prev.skills = sorted(list(set(prev.skills + chunk.skills)))
                if prev_len < self.min_chunk_chars and chunk.section_title and chunk.section_title != "基本資料":
                    prev.section_title = chunk.section_title
                prev.company = prev.company or chunk.company
                prev.job_title = prev.job_title or chunk.job_title
                if prev_len < self.min_chunk_chars and chunk.chunk_type not in (ChunkType.OTHER, ChunkType.PROFILE):
                    prev.chunk_type = chunk.chunk_type
            else:
                merged.append(chunk)

        # 重新編號 chunk_id
        for idx, c in enumerate(merged):
            c.chunk_id = f"{candidate_id}:{idx}"

        return merged
