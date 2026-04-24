"""稠密索引写入模块。"""

from __future__ import annotations

import logging
from typing import Protocol

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.retrieval.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


class DenseIndexWriter(Protocol):
    """稠密索引写入器协议。"""

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """写入或更新稠密索引块。"""

    def delete_file(self, file_id: str) -> None:
        """删除指定文件的所有稠密索引块。"""


class ChromaDenseIndexWriter:
    """基于 ChromaDB 的稠密索引写入器。"""

    def __init__(self, settings: Settings, embedding: EmbeddingProvider) -> None:
        self._persist_directory = settings.persist_directory
        self._embedding = embedding
        self._collection_name = "local_files"

        # 初始化 Chroma 客户端
        self._client = chromadb.PersistentClient(path=self._persist_directory)
        
        # 为了复用 Langchain 的包装（处理批次等），我们可以创建包装器
        # 但这会导致我们只能用 Document。我们自己来直接调用 self._db 会更好一点，
        # 或者使用 langchain_chroma.Chroma。
        self._db = Chroma(
            client=self._client,
            collection_name=self._collection_name,
            embedding_function=self._embedding,
            collection_metadata={"hnsw:space": "cosine"}
        )

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        if not chunks:
            return

        documents = []
        ids = []

        for chunk in chunks:
            # Dense retriever 需要的是 chunk_id 和 embedding_text
            # Langchain Chroma API 需要 Document 及其 metadata
            doc = Document(
                page_content=chunk.embedding_text,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "file_id": chunk.file_id,
                    "filepath": chunk.filepath,
                    "filename": chunk.filename,
                    "source_type": chunk.source_type,
                    "filetype": chunk.filetype,
                    "chunk_type": chunk.chunk_type,
                    "mtime": chunk.mtime,
                    "ctime": chunk.ctime,
                    # 将其他原始元数据合并
                    **chunk.metadata
                }
            )
            documents.append(doc)
            ids.append(chunk.chunk_id)

        try:
            # Langchain_Chroma 提供 add_documents，它会自动处理 id 如果不提供
            # 但我们为了更新已有记录，必须显式提供 ids
            self._db.add_documents(documents=documents, ids=ids)
            logger.debug("成功 upsert %d 个稠密索引块", len(chunks))
        except Exception as exc:
            logger.error("写入稠密索引失败: %s", exc)
            raise

    def delete_file(self, file_id: str) -> None:
        if not file_id:
            return

        try:
            # ChromaDB 支持按 metadata where 进行删除
            # _client.get_collection 直接执行删除最保险
            collection = self._client.get_collection(self._collection_name)
            collection.delete(where={"file_id": file_id})
            logger.debug("已删除 file_id='%s' 的稠密索引", file_id)
        except ValueError:
            # Collection 不存在时，不需要处理
            pass
        except Exception as exc:
            logger.error("删除稠密索引 (file_id=%s) 失败: %s", file_id, exc)
