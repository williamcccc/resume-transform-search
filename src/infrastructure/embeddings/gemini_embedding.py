import os
from typing import List, Optional
from src.domain.interfaces import IEmbeddingService
from src.infrastructure.transformers.utils import retry_call


class GeminiEmbeddingService(IEmbeddingService):
    """
    使用 Google Gemini API (gemini-embedding-001) 的文本向量化實作
    - 支援 768 維度降維 (output_dimensionality=768)
    - 支援批次切片向量化 (Batch Embedding) 與重試機制
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-embedding-001",
        dim: int = 768,
        batch_size: int = 20,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model_name
        self.dim = dim
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("未設定 GEMINI_API_KEY，無法初始化向量化服務。")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def embed_texts(self, texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
        if not texts:
            return []

        from google.genai import types

        client = self._get_client()
        task_type_upper = task_type.upper()
        if not task_type_upper.startswith("RETRIEVAL_"):
            task_type_upper = f"RETRIEVAL_{task_type_upper}"

        config = types.EmbedContentConfig(
            output_dimensionality=self.dim,
            task_type=task_type_upper,
        )

        all_vectors: List[List[float]] = []

        # 批次處理以防止超時或單次 Payload 過大
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            # 過濾空字串或純空白，空字串用佔位符避免 API 報錯
            cleaned_batch = [t.strip() if t.strip() else "無內文" for t in batch]

            def _call():
                return client.models.embed_content(
                    model=self.model_name,
                    contents=cleaned_batch,
                    config=config,
                )

            res = retry_call(
                _call,
                max_retries=self.max_retries,
                initial_delay=self.retry_delay,
                op_name=f"gemini_embedding_batch ({len(cleaned_batch)} items)",
            )
            if hasattr(res, "embeddings") and res.embeddings:
                for emb in res.embeddings:
                    all_vectors.append(list(emb.values))
            else:
                raise RuntimeError(f"Gemini 向量化 API 未回傳有效 embeddings 物件: {res}")

        return all_vectors

    def embed_query(self, query: str) -> List[float]:
        if not query or not query.strip():
            query = "求職者"
        vectors = self.embed_texts([query.strip()], task_type="retrieval_query")
        return vectors[0]
