"""Dense 索引生命周期管理。"""

from __future__ import annotations

import logging

import chromadb

logger = logging.getLogger(__name__)

COLLECTION_NAME = "local_files"


def reset_dense_collection(persist_directory: str, collection_name: str = COLLECTION_NAME) -> None:
    """删除并重建 Chroma collection，用于全量重建前清理旧向量。"""
    client = chromadb.PersistentClient(path=persist_directory)
    try:
        client.delete_collection(collection_name)
        logger.info("已删除旧 Dense collection: %s", collection_name)
    except (ValueError, chromadb.errors.NotFoundError):
        logger.info("Dense collection 不存在，跳过删除: %s", collection_name)
