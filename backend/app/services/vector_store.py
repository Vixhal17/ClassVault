from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

COLLECTION_NAME = "classvault_chunks"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_DIMENSION = 384  # for sentence-transformers/all-MiniLM-L6-v2


class DocumentChunk(BaseModel):
    chunk_index: int
    text: str
    page: int
    file_id: str
    file_name: str
    unit_id: str
    course_id: str


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    score: float
    page: int
    file_id: str
    file_name: str
    unit_id: str
    course_id: str


class BaseVectorStore(ABC):
    @abstractmethod
    async def ensure_collection(self) -> None:
        """Ensure collection/index exists with appropriate schema."""
        pass

    @abstractmethod
    async def upsert_chunks(
        self,
        course_id: str,
        unit_id: str,
        file_id: str,
        file_name: str,
        chunks: List[DocumentChunk],
    ) -> int:
        """Embed and upsert document chunks."""
        pass

    @abstractmethod
    async def delete_file_chunks(self, file_id: str) -> None:
        """Delete all chunks belonging to a file."""
        pass

    @abstractmethod
    async def search(
        self,
        course_id: str,
        query: str,
        top_k: int = 8,
        unit_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """Search relevant chunks for a question."""
        pass


class EmbeddingService:
    """Manages dense and sparse embedding models using fastembed."""

    _instance = None
    _dense_model = None
    _sparse_model = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_dense_model(self):
        if self._dense_model is None:
            from fastembed import TextEmbedding

            # Default model: sentence-transformers/all-MiniLM-L6-v2
            self._dense_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        return self._dense_model

    def _get_sparse_model(self):
        if self._sparse_model is None:
            from fastembed import SparseTextEmbedding

            self._sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        return self._sparse_model

    def embed_dense(self, texts: List[str]) -> List[List[float]]:
        model = self._get_dense_model()
        return [vec.tolist() for vec in model.embed(texts)]

    def embed_sparse(self, texts: List[str]) -> List[Dict[str, Any]]:
        model = self._get_sparse_model()
        results = []
        for sparse in model.embed(texts):
            results.append({
                "indices": sparse.indices.tolist(),
                "values": sparse.values.tolist(),
            })
        return results


class QdrantVectorStore(BaseVectorStore):
    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.QDRANT_URL
        self.client = AsyncQdrantClient(self.url, check_compatibility=False)
        self.embedder = EmbeddingService.get_instance()
        self._initialized = False

    async def ensure_collection(self) -> None:
        if self._initialized:
            return

        collections = await self.client.get_collections()
        existing_names = [c.name for c in collections.collections]

        if COLLECTION_NAME not in existing_names:
            logger.info(f"Creating Qdrant collection '{COLLECTION_NAME}' with dense and sparse vectors...")
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    DENSE_VECTOR_NAME: qmodels.VectorParams(
                        size=DENSE_DIMENSION,
                        distance=qmodels.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()
                },
            )

            # Create payload indices for fast filtering by course_id, unit_id, and file_id
            await self.client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="course_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="file_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="unit_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
        self._initialized = True

    async def upsert_chunks(
        self,
        course_id: str,
        unit_id: str,
        file_id: str,
        file_name: str,
        chunks: List[DocumentChunk],
    ) -> int:
        if not chunks:
            return 0

        await self.ensure_collection()

        texts = [chunk.text for chunk in chunks]
        dense_embeddings = self.embedder.embed_dense(texts)
        sparse_embeddings = self.embedder.embed_sparse(texts)

        points = []
        for i, chunk in enumerate(chunks):
            # Deterministic UUID per chunk
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_id}_{chunk.chunk_index}"))
            sparse_dict = sparse_embeddings[i]

            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector={
                        DENSE_VECTOR_NAME: dense_embeddings[i],
                        SPARSE_VECTOR_NAME: qmodels.SparseVector(
                            indices=sparse_dict["indices"],
                            values=sparse_dict["values"],
                        ),
                    },
                    payload={
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                        "page": chunk.page,
                        "file_id": file_id,
                        "file_name": file_name,
                        "unit_id": unit_id,
                        "course_id": course_id,
                    },
                )
            )

        # Batch upsert
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch,
                wait=True,
            )

        return len(points)

    async def delete_file_chunks(self, file_id: str) -> None:
        await self.ensure_collection()
        await self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="file_id",
                            match=qmodels.MatchValue(value=str(file_id)),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def search(
        self,
        course_id: str,
        query: str,
        top_k: int = 8,
        unit_id: Optional[str] = None,
    ) -> List[SearchResult]:
        await self.ensure_collection()

        # Build filter conditions
        must_conditions = [
            qmodels.FieldCondition(
                key="course_id",
                match=qmodels.MatchValue(value=str(course_id)),
            )
        ]
        if unit_id:
            must_conditions.append(
                qmodels.FieldCondition(
                    key="unit_id",
                    match=qmodels.MatchValue(value=str(unit_id)),
                )
            )
        query_filter = qmodels.Filter(must=must_conditions)

        dense_query = self.embedder.embed_dense([query])[0]
        sparse_query = self.embedder.embed_sparse([query])[0]

        if settings.RAG_HYBRID_ENABLED:
            # Hybrid search via prefetch + reciprocal rank fusion (RRF)
            try:
                response = await self.client.query_points(
                    collection_name=COLLECTION_NAME,
                    prefetch=[
                        qmodels.Prefetch(
                            query=dense_query,
                            using=DENSE_VECTOR_NAME,
                            filter=query_filter,
                            limit=top_k * 2,
                        ),
                        qmodels.Prefetch(
                            query=qmodels.SparseVector(
                                indices=sparse_query["indices"],
                                values=sparse_query["values"],
                            ),
                            using=SPARSE_VECTOR_NAME,
                            filter=query_filter,
                            limit=top_k * 2,
                        ),
                    ],
                    query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                    limit=top_k,
                )
                points = response.points
            except Exception as e:
                logger.warning(f"Hybrid query_points fallback to dense search: {e}")
                resp = await self.client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=dense_query,
                    using=DENSE_VECTOR_NAME,
                    query_filter=query_filter,
                    limit=top_k,
                )
                points = resp.points
        else:
            resp = await self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=dense_query,
                using=DENSE_VECTOR_NAME,
                query_filter=query_filter,
                limit=top_k,
            )
            points = resp.points

        results = []
        for pt in points:
            payload = pt.payload or {}
            results.append(
                SearchResult(
                    chunk_id=str(pt.id),
                    text=payload.get("text", ""),
                    score=float(pt.score) if hasattr(pt, "score") and pt.score is not None else 0.0,
                    page=payload.get("page", 1),
                    file_id=payload.get("file_id", ""),
                    file_name=payload.get("file_name", ""),
                    unit_id=payload.get("unit_id", ""),
                    course_id=payload.get("course_id", ""),
                )
            )
        return results


class FakeVectorStore(BaseVectorStore):
    """In-memory mock vector store for unit tests without Qdrant."""

    def __init__(self):
        self.chunks: Dict[str, DocumentChunk] = {}

    async def ensure_collection(self) -> None:
        pass

    async def upsert_chunks(
        self,
        course_id: str,
        unit_id: str,
        file_id: str,
        file_name: str,
        chunks: List[DocumentChunk],
    ) -> int:
        for chunk in chunks:
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_id}_{chunk.chunk_index}"))
            self.chunks[chunk_id] = chunk
        return len(chunks)

    async def delete_file_chunks(self, file_id: str) -> None:
        self.chunks = {k: v for k, v in self.chunks.items() if v.file_id != str(file_id)}

    async def search(
        self,
        course_id: str,
        query: str,
        top_k: int = 8,
        unit_id: Optional[str] = None,
    ) -> List[SearchResult]:
        results = []
        for cid, chunk in self.chunks.items():
            if chunk.course_id != str(course_id):
                continue
            if unit_id and chunk.unit_id != str(unit_id):
                continue
            # Simple substring matching score for mock
            score = 1.0 if any(w.lower() in chunk.text.lower() for w in query.split()) else 0.1
            results.append(
                SearchResult(
                    chunk_id=cid,
                    text=chunk.text,
                    score=score,
                    page=chunk.page,
                    file_id=chunk.file_id,
                    file_name=chunk.file_name,
                    unit_id=chunk.unit_id,
                    course_id=chunk.course_id,
                )
            )
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]


# Singleton instance
vector_store: BaseVectorStore = QdrantVectorStore()


def get_vector_store() -> BaseVectorStore:
    return vector_store
