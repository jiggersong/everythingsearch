"""独立全量索引器（专供 Pipeline 双写使用）。"""

import hashlib
import logging
import time

from pathlib import Path
from everythingsearch.infra.settings import get_settings, require_dashscope_api_key, require_target_dirs, apply_sdk_environment
from everythingsearch.logging_config import setup_cli_logging
from everythingsearch.indexer import scan_files, scan_mweb_notes
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.dense_index_writer import ChromaDenseIndexWriter
from everythingsearch.indexing.file_scanner import (
    scan_disk_files_for_index,
    scan_mweb_notes_for_index,
)
from everythingsearch.indexing.progress_estimator import (
    IndexScaleSnapshot,
    estimate_cost_from_chunks,
    estimate_full_cost_from_file_count,
    load_historical_chunks_per_file,
)
from everythingsearch.indexing.progress_reporter import (
    IndexProgressReporter,
    IndexProgressState,
)
from everythingsearch.indexing.sparse_index_writer import SQLiteSparseIndexWriter
from everythingsearch.retrieval.embedding import DashScopeEmbeddingProvider

logger = logging.getLogger(__name__)

def generate_file_id(filepath: str) -> str:
    """基于文件路径生成稳定的 file_id。"""
    return hashlib.md5(filepath.encode("utf-8")).hexdigest()

def build_pipeline_index(
    initial_scale_snapshot: IndexScaleSnapshot | None = None,
    transition_reason: str | None = None,
):
    """构建专属于新版 Pipeline 的底层索引。
    
    复用原版的扫描逻辑获得 langchain Document，
    将其适配为 IndexedChunk 并双写到 FTS5 与 ChromaDB。
    """
    settings = get_settings()
    require_target_dirs(settings)
    require_dashscope_api_key(settings)
    apply_sdk_environment(settings)
    
    if transition_reason:
        logger.info("全量索引触发原因: %s", transition_reason)
    total_start = time.time()

    if initial_scale_snapshot is None:
        disk_files = scan_disk_files_for_index()
        mweb_notes = scan_mweb_notes_for_index()
        initial_scale_snapshot = IndexScaleSnapshot(
            disk_file_count=len(disk_files),
            mweb_note_count=len(mweb_notes),
            pending_file_count=len(disk_files) + len(mweb_notes),
        )
    file_count = initial_scale_snapshot.disk_file_count + initial_scale_snapshot.mweb_note_count
    chunks_per_file = load_historical_chunks_per_file(
        settings.sparse_index_path,
        fallback_file_count=file_count,
    )
    initial_estimate = estimate_full_cost_from_file_count(
        file_count=file_count,
        historical_chunks_per_file=chunks_per_file,
    )
    reporter = IndexProgressReporter("全量索引构建", logger)
    reporter.start(
        IndexProgressState(
            phase_name="扫描与解析文件",
            total_file_count=file_count,
            pending_file_count=file_count,
            estimated_total_chunk_count=initial_estimate.estimated_chunk_count,
            estimated_total_token_count=initial_estimate.estimated_input_token_count,
        ),
        initial_estimate,
    )
    
    # 1. 扫描文件
    print("正在扫描本地文件...")
    logger.info("开始扫描本地文件。")
    docs, _ = scan_files(progress_reporter=reporter)

    print("正在扫描 MWeb 笔记...")
    logger.info("开始扫描 MWeb 笔记。")
    mweb_docs, _ = scan_mweb_notes(progress_reporter=reporter)
    docs.extend(mweb_docs)

    if not docs:
        logger.warning("未扫描到任何文档内容，构建终止。")
        reporter.finish()
        return

    print(f"扫描完成，共 {len(docs)} 个 chunk")
    logger.info("扫描完成，共获取到 %d 个 Chunk。", len(docs))
    reporter.scanning_complete()
    
    # 2. 转换数据模型
    chunks_to_write = []
    
    # 为了保证同一个文件的不同类型 chunk 有唯一 chunk_id
    file_counters = {}
    
    for doc in docs:
        meta = doc.metadata.copy()
        filepath = meta.get("source", "")
        file_id = generate_file_id(filepath)
        
        # 获取或分配 chunk_idx
        chunk_type = meta.get("chunk_type", "content")
        
        if chunk_type == "content":
            chunk_idx = meta.get("chunk_idx", 0)
            chunk_suffix = f"c{chunk_idx}"
        elif chunk_type == "filename":
            chunk_suffix = "fn"
        elif chunk_type == "heading":
            # 可能有多个 heading chunk
            count = file_counters.get(f"{file_id}_heading", 0)
            chunk_suffix = f"h{count}"
            file_counters[f"{file_id}_heading"] = count + 1
        else:
            count = file_counters.get(f"{file_id}_{chunk_type}", 0)
            chunk_suffix = f"x{count}"
            file_counters[f"{file_id}_{chunk_type}"] = count + 1
            
        chunk_id = f"{file_id}_{chunk_suffix}"
        
        # 移除会被强类型化的元数据
        filename = meta.pop("filename", "")
        source_type = meta.pop("source_type", "file")
        filetype = meta.pop("type", "")
        title_path_list = meta.pop("title_path", [])
        title_path = tuple(title_path_list) if title_path_list else ()
        meta.pop("chunk_type", None)
        mtime = float(meta.pop("mtime", 0.0))
        ctime = float(meta.pop("ctime", 0.0))
        meta.pop("source", None)
        
        indexed_chunk = IndexedChunk(
            chunk_id=chunk_id,
            file_id=file_id,
            filepath=filepath,
            filename=filename,
            source_type=source_type,
            filetype=filetype,
            chunk_type=chunk_type,
            title_path=title_path,
            content=doc.page_content,
            embedding_text=doc.page_content,
            sparse_text=doc.page_content,
            chunk_index=meta.get("chunk_idx", 0),
            mtime=mtime,
            ctime=ctime,
            metadata=meta
        )
        chunks_to_write.append(indexed_chunk)

    refined_estimate = estimate_cost_from_chunks(chunks_to_write)
    reporter.update_estimate(refined_estimate)
        
    # 3. 双写持久化
    print("开始双写索引 (Sparse + Dense)...")
    logger.info("开始双写索引 (Sparse & Dense)。")

    # 删除旧的 sparse db 以加速
    sparse_db_path = Path(settings.sparse_index_path)
    if sparse_db_path.exists():
        sparse_db_path.unlink()
        logger.info("已删除旧的 Sparse DB: %s", sparse_db_path)
    
    # 实例化 Writers
    sparse_writer = SQLiteSparseIndexWriter(settings)
    embedding_provider = DashScopeEmbeddingProvider(settings)
    dense_writer = ChromaDenseIndexWriter(settings, embedding_provider)
    
    # 分批写入
    try:
        reporter.update_phase("Sparse Index 写入")
        logger.info("写入 Sparse Index (SQLite FTS5)。")
        batch_size = settings.indexer_batch_size
        for i in range(0, len(chunks_to_write), batch_size):
            batch = chunks_to_write[i:i+batch_size]
            sparse_writer.upsert_chunks(batch)
            reporter.add_sparse_chunks(len(batch))
            logger.info("已写入 Sparse Batch: %d / %d", min(i+batch_size, len(chunks_to_write)), len(chunks_to_write))
        logger.info("Sparse Index 写入完成，开始 optimize。")
        with reporter.blocking_phase("Sparse Index optimize"):
            sparse_writer.optimize()
    except Exception as exc:
        logger.error("Sparse 索引构建失败: %s", exc)
        reporter.finish()
        return
        
    try:
        reporter.update_phase("Dense Index 写入")
        print("写入 Dense 索引 (调用 Embedding API，请耐心等待)...")
        logger.info("写入 Dense Index (ChromaDB API)，调用大模型接口。")
        batch_size = settings.indexer_batch_size
        with reporter.blocking_phase("Dense Index 写入"):
            for i in range(0, len(chunks_to_write), batch_size):
                batch = chunks_to_write[i:i+batch_size]
                dense_writer.upsert_chunks(batch)
                reporter.add_dense_chunks(len(batch))
                embedding_stats = embedding_provider.stats_snapshot()
                reporter.set_embedding_stats(
                    embedding_stats.cache_hit_text_count,
                    embedding_stats.uncached_text_count,
                    embedding_stats.remote_batch_count,
                )
                logger.info("已写入 Dense Batch: %d / %d", min(i+batch_size, len(chunks_to_write)), len(chunks_to_write))
        logger.info("Dense Index 写入完成。")
    except Exception as exc:
        logger.error("Dense 索引构建失败: %s", exc)
        reporter.finish()
        return
        
    duration = time.time() - total_start
    logger.info("Pipeline 索引全量构建完成！总耗时: %.2f 秒", duration)
    reporter.finish()

if __name__ == "__main__":
    setup_cli_logging()
    build_pipeline_index()
