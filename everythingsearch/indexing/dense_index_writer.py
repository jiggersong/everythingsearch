"""稠密索引写入模块。"""

from __future__ import annotations

import json
import logging
from typing import Protocol

import chromadb

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.dense_lifecycle import COLLECTION_NAME
from everythingsearch.retrieval.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)

# Dense 仅存占位 document，正文由 ChunkStore（sparse_chunks）回表。
DENSE_DOCUMENT_PLACEHOLDER = " "


class DenseIndexWriter(Protocol):
    """稠密索引写入器协议。"""

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """写入或更新稠密索引块。"""

    def delete_file(self, file_id: str) -> None:
        """删除指定文件的所有稠密索引块。"""


_chroma_client_cache: dict[str, chromadb.PersistentClient] = {}


def _get_chroma_client(persist_directory: str) -> chromadb.PersistentClient:
    """获取或初始化 ChromaDB Client（单例），避免重复实例化导致内存泄漏。"""
    import os

    path = os.path.abspath(persist_directory)
    if path not in _chroma_client_cache:
        _chroma_client_cache[path] = chromadb.PersistentClient(path=path)
    return _chroma_client_cache[path]


class ChromaDenseIndexWriter:
    """基于 ChromaDB 的稠密索引写入器（预计算向量 + 最小 metadata）。"""

    def __init__(self, settings: Settings, embedding: EmbeddingProvider) -> None:
        self._persist_directory = settings.persist_directory
        self._embedding = embedding
        self._collection_name = COLLECTION_NAME
        self._client = _get_chroma_client(self._persist_directory)

    def _get_collection(self):
        return self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        if not chunks:
            return

        texts = [chunk.embedding_text for chunk in chunks]
        vectors = self._embedding.embed_documents(texts)
        ids = [chunk.chunk_id for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            metadatas.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "file_id": chunk.file_id,
                    "filepath": chunk.filepath,
                    "filename": chunk.filename,
                    "source_type": chunk.source_type,
                    "filetype": chunk.filetype,
                    "chunk_type": chunk.chunk_type,
                    "mtime": chunk.mtime,
                    "ctime": chunk.ctime,
                    "chunk_idx": chunk.chunk_index,
                    "title_path": json.dumps(chunk.title_path, ensure_ascii=False),
                }
            )

        try:
            collection = self._get_collection()
            collection.upsert(
                ids=ids,
                embeddings=vectors,
                metadatas=metadatas,
                documents=[DENSE_DOCUMENT_PLACEHOLDER] * len(chunks),
            )
            logger.debug("成功 upsert %d 个稠密索引块", len(chunks))
        except Exception as exc:
            logger.error("写入稠密索引失败: %s", exc)
            raise

    def delete_file(self, file_id: str) -> None:
        if not file_id:
            return

        try:
            collection = self._client.get_collection(self._collection_name)
            collection.delete(where={"file_id": file_id})
            logger.debug("已删除 file_id='%s' 的稠密索引", file_id)
        except (ValueError, chromadb.errors.NotFoundError):
            pass
        except Exception as exc:
            logger.error("删除稠密索引 (file_id=%s) 失败: %s", file_id, exc)
