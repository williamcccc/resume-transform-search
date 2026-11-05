import hashlib
import os
from pathlib import Path
from typing import List, Optional
from src.application.dto import IndexCommand, IndexResult
from src.domain.interfaces import IMarkdownChunker, IEmbeddingService, IVectorStore
from src.domain.models import ResumeChunk


class IndexResumesUseCase:
    """
    履歷切片、向量化與 Redis 索引核心使用案例
    """

    def __init__(
        self,
        chunker: IMarkdownChunker,
        embedding_service: IEmbeddingService,
        vector_store: IVectorStore,
    ):
        self.chunker = chunker
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def execute(self, command: IndexCommand) -> IndexResult:
        # 1. 確保向量資料庫索引已就緒
        embedding_dim = getattr(self.embedding_service, "dim", 768)
        self.vector_store.ensure_index(dim=embedding_dim, recreate=command.recreate_index)

        # 2. 收集欲處理之目標描述元 (延遲載入以維持 O(1) 記憶體與磁碟 I/O 能效)
        # 結構: (candidate_id, Optional[Path], Optional[str])
        descriptors: List[tuple[str, Optional[Path], Optional[str]]] = []

        if command.markdown_text:
            cand_id = command.candidate_id or "candidate"
            descriptors.append((cand_id, None, command.markdown_text))

        elif command.file_path:
            p = Path(command.file_path)
            if not p.exists() or not p.is_file():
                return IndexResult(
                    total_files=0,
                    indexed_files=0,
                    total_chunks=0,
                    errors=[f"指定的檔案不存在: {p}"],
                )
            descriptors.append((p.stem, p, None))

        elif command.dir_path:
            d = Path(command.dir_path)
            if not d.exists() or not d.is_dir():
                return IndexResult(
                    total_files=0,
                    indexed_files=0,
                    total_chunks=0,
                    errors=[f"指定的目錄不存在: {d}"],
                )
            for f in sorted(d.rglob("*.md"), key=lambda x: str(x).lower()):
                if f.is_file():
                    descriptors.append((f.stem, f, None))

        # 若有指定 limit 限制筆數，於讀檔前進行截斷，避免無謂的磁碟讀取與 RAM 佔用
        if command.limit and command.limit > 0:
            descriptors = descriptors[:command.limit]

        total_files = len(descriptors)

        indexed_files = 0
        skipped_files = 0
        total_chunks = 0
        errors: List[str] = []

        # 3. 逐一檔案延遲串流讀取、切片、向量化與入庫
        for cand_id, file_path_obj, in_memory_text in descriptors:
            try:
                # 延遲串流讀取：當前迴圈處理該檔案時才讀入字串，完成後自動脫離作用域供 GC 回收
                if in_memory_text is not None:
                    md_text = in_memory_text
                    file_path = None
                else:
                    md_text = file_path_obj.read_text(encoding="utf-8", errors="replace")
                    file_path = str(file_path_obj)

                # 計算內容指紋 (SHA-256)
                current_hash = hashlib.sha256(md_text.encode("utf-8")).hexdigest()

                # 增量快取比對：若未指定 force 或 recreate，且內容未變更則跳過 API 向量化
                if not command.force and not command.recreate_index:
                    existing_hash = self.vector_store.get_candidate_hash(cand_id)
                    if existing_hash and existing_hash == current_hash:
                        skipped_files += 1
                        continue

                chunks: List[ResumeChunk] = self.chunker.chunk_markdown(
                    markdown=md_text,
                    candidate_id=cand_id,
                    file_path=file_path,
                )
                if not chunks:
                    continue

                for chunk in chunks:
                    chunk.content_hash = current_hash

                # 組裝語意豐富的嵌入文本 (候選人姓名 + 區塊標題 + 內文)
                texts_to_embed = [
                    f"{chunk.candidate_name} - {chunk.section_title}\n{chunk.content}"
                    for chunk in chunks
                ]

                # 呼叫向量化服務 (支援批次處理)
                vectors = self.embedding_service.embed_texts(
                    texts=texts_to_embed,
                    task_type="retrieval_document",
                )

                for chunk, vec in zip(chunks, vectors):
                    chunk.vector = vec

                # 刪除既有舊切片以保證等冪性 (Idempotent)
                self.vector_store.delete_by_candidate(cand_id)

                # 寫入 Redis
                inserted = self.vector_store.upsert_chunks(chunks)
                self.vector_store.set_candidate_hash(cand_id, current_hash)
                total_chunks += inserted
                indexed_files += 1

            except Exception as e:
                errors.append(f"處理候選人 [{cand_id}] 時失敗: {str(e)}")

        return IndexResult(
            total_files=total_files,
            indexed_files=indexed_files,
            total_chunks=total_chunks,
            errors=errors,
            skipped_files=skipped_files,
        )
