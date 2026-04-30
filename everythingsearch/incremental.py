"""
Incremental indexing: track file changes via SQLite and update ChromaDB partially.

Usage (from repo root):
    python -m everythingsearch.incremental              # incremental update
    python -m everythingsearch.incremental --full       # full rebuild
    ./venv/bin/python everythingsearch/incremental.py   # same, if root is cwd
"""

import os
import sys
import time
import sqlite3
import subprocess
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# 直接执行 `python everythingsearch/incremental.py` 时，sys.path 里只有包目录；
# 这里补上仓库根目录，保证绝对包导入和 legacy config 兼容加载都可用。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from everythingsearch.indexer import (
    _init_scan_cache,
    _save_cached_docs,
    build_documents_for_path_cached,
)
from everythingsearch.embedding_cache import CachedEmbeddings
from everythingsearch.infra.settings import (
    apply_sdk_environment,
    get_settings,
    require_dashscope_api_key,
    require_target_dirs,
)
from everythingsearch.logging_config import setup_cli_logging
from everythingsearch.indexing.file_scanner import (
    scan_disk_files_for_index,
    scan_mweb_notes_for_index,
)
from everythingsearch.indexing.progress_estimator import (
    IndexScaleSnapshot,
    estimate_incremental_cost,
    estimate_tokens_from_texts,
    load_historical_chunks_per_file,
)
from everythingsearch.indexing.progress_reporter import (
    IndexProgressReporter,
    IndexProgressState,
)
from everythingsearch.indexing.sparse_index_writer import SQLiteSparseIndexWriter
from everythingsearch.indexing.pipeline_indexer import generate_file_id
from everythingsearch.indexing.chunk_models import IndexedChunk
from langchain_chroma import Chroma
import chromadb

logger = logging.getLogger(__name__)


def _init_state_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_index (
            filepath TEXT PRIMARY KEY,
            mtime REAL,
            source_type TEXT,
            indexed_at REAL
        )
    """)
    conn.commit()


# 迁移兼容层：以下两个 wrapper 仅保留用于兼容旧代码和测试，
# 新代码应直接从 everythingsearch.indexing.file_scanner 导入。
def _scan_disk_files() -> dict[str, tuple[float, str]]:
    """Scan TARGET_DIR(s) and return {filepath: (mtime, 'file')}."""
    return scan_disk_files_for_index()


def _scan_disk_mweb() -> dict[str, tuple[float, str]]:
    """Scan MWEB_DIR and return {filepath: (mtime, 'mweb')}."""
    return scan_mweb_notes_for_index()


def _load_db_state(conn: sqlite3.Connection) -> dict[str, tuple[float, str]]:
    """Load all tracked files from the state database."""
    rows = conn.execute("SELECT filepath, mtime, source_type FROM file_index").fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def _delete_chunks(collection, filepath: str, sparse_writer: SQLiteSparseIndexWriter = None):
    """Delete all ChromaDB and FTS5 chunks belonging to a file."""
    try:
        collection.delete(where={"source": filepath})
    except Exception:
        pass
    
    if sparse_writer:
        try:
            # Assuming sparse_writer has a delete_file_by_path or similar method
            # Since we only have file_id in pipeline_indexer, let's generate it
            file_id = generate_file_id(filepath)
            sparse_writer.delete_file(file_id)
        except Exception as e:
            logger.warning(f"删除 Sparse 索引失败 {filepath}: {e}")


def run_incremental():
    try:
        _run_incremental_impl()
    except KeyboardInterrupt:
        print("\n用户中断，索引已停止。")
        logger.info("用户中断索引操作。")
        sys.exit(1)


def _run_incremental_impl():
    settings = get_settings()
    require_target_dirs(settings)
    require_dashscope_api_key(settings)
    apply_sdk_environment(settings)
    db_path = settings.index_state_db
    total_start = time.time()

    if settings.enable_mweb and settings.mweb_export_script and os.path.isfile(settings.mweb_export_script):
        print("正在运行 MWeb 导出...")
        logger.info("开始运行 MWeb 导出脚本。")
        try:
            subprocess.run(
                [sys.executable, settings.mweb_export_script],
                check=True,
                timeout=120,
            )
            logger.info("MWeb 导出完成。")
        except Exception as e:
            logger.warning("MWeb 导出失败，继续使用已有文件: %s", e)

    conn = sqlite3.connect(db_path)
    _init_state_db(conn)

    print("正在扫描文件系统...")
    logger.info("开始扫描文件系统。")
    disk_files = _scan_disk_files()
    disk_mweb = _scan_disk_mweb()
    logger.info("扫描到文件数: %s, MWeb 笔记数: %s", len(disk_files), len(disk_mweb))
    print(f"  文件: {len(disk_files)}  笔记: {len(disk_mweb)}")

    disk_all = {**disk_files, **disk_mweb}
    db_state = _load_db_state(conn)

    new_paths = []
    modified_paths = []
    deleted_paths = []

    for fp, (mtime, stype) in disk_all.items():
        if fp not in db_state:
            new_paths.append(fp)
        elif abs(db_state[fp][0] - mtime) > 0.01:
            modified_paths.append(fp)

    for fp in db_state:
        if fp not in disk_all:
            deleted_paths.append(fp)

    logger.info("变更统计: 新增=%s, 修改=%s, 删除=%s", len(new_paths), len(modified_paths), len(deleted_paths))
    print(f"变更: +{len(new_paths)} ~{len(modified_paths)} -{len(deleted_paths)}  (新增/修改/删除)")

    if not new_paths and not modified_paths and not deleted_paths:
        print("索引已是最新，无需更新。")
        logger.info("索引已是最新，无需更新。")
        conn.close()
        return

    to_index = modified_paths + new_paths
    scale_snapshot = IndexScaleSnapshot(
        disk_file_count=len(disk_files),
        mweb_note_count=len(disk_mweb),
        new_file_count=len(new_paths),
        modified_file_count=len(modified_paths),
        deleted_file_count=len(deleted_paths),
        pending_file_count=len(to_index) + len(deleted_paths),
        existing_state_file_count=len(db_state),
    )
    chunks_per_file = load_historical_chunks_per_file(
        settings.sparse_index_path,
        fallback_file_count=len(db_state),
    )
    estimate = estimate_incremental_cost(
        pending_file_count=len(to_index),
        historical_chunks_per_file=chunks_per_file,
    )

    client = chromadb.PersistentClient(path=settings.persist_directory)
    existing_collections = [c.name for c in client.list_collections()]

    if "local_files" not in existing_collections:
        logger.warning("现有 Dense collection 不存在，增量更新无法执行，将切换为全量索引构建。")
        conn.close()
        from everythingsearch.indexing.pipeline_indexer import build_pipeline_index
        build_pipeline_index(
            initial_scale_snapshot=scale_snapshot,
            transition_reason="Dense collection 不存在",
        )
        _rebuild_state_db()
        return

    reporter = IndexProgressReporter("增量索引更新", logger)
    reporter.start(
        IndexProgressState(
            phase_name="准备索引更新",
            total_file_count=len(disk_all),
            pending_file_count=scale_snapshot.pending_file_count,
            estimated_total_chunk_count=estimate.estimated_chunk_count,
            estimated_total_token_count=estimate.estimated_input_token_count,
        ),
        estimate,
    )

    collection = client.get_collection("local_files")

    embeddings = CachedEmbeddings(
        model=settings.embedding_model,
        cache_path=settings.embedding_cache_path,
    )
    vectordb = Chroma(
        client=client,
        embedding_function=embeddings,
        collection_name="local_files",
    )

    sparse_writer = SQLiteSparseIndexWriter(settings)

    if deleted_paths:
        reporter.update_phase("删除已移除文件索引")
        print(f"正在删除 {len(deleted_paths)} 个已移除文件的索引...")
        logger.info("开始删除 %s 个已移除文件的索引。", len(deleted_paths))
        deleted_batch_count = 0
        for fp in deleted_paths:
            _delete_chunks(collection, fp, sparse_writer)
            conn.execute("DELETE FROM file_index WHERE filepath = ?", (fp,))
            deleted_batch_count += 1
            if deleted_batch_count >= 50:
                reporter.add_deleted_files(deleted_batch_count)
                deleted_batch_count = 0
        if deleted_batch_count:
            reporter.add_deleted_files(deleted_batch_count)
        conn.commit()
        # 同步清理扫描缓存，避免缓存膨胀
        cache_path = settings.scan_cache_path
        if cache_path:
            from everythingsearch.indexer import _init_scan_cache
            scan_conn = sqlite3.connect(cache_path, timeout=30)
            _init_scan_cache(scan_conn)
            for fp in deleted_paths:
                scan_conn.execute("DELETE FROM scan_cache WHERE filepath = ?", (fp,))
            scan_conn.commit()
            scan_conn.close()
        logger.info("删除完成。")

    scan_cache_conn = None
    if to_index:
        reporter.update_phase("新增与修改文件索引")
        cache_path = settings.scan_cache_path
        scan_cache_conn = sqlite3.connect(cache_path, timeout=30) if cache_path else None
        if scan_cache_conn:
            from everythingsearch.indexer import _init_scan_cache
            _init_scan_cache(scan_cache_conn)
        print(f"正在索引 {len(to_index)} 个文件 ({len(modified_paths)} 修改 + {len(new_paths)} 新增)...")
        logger.info(
            "开始索引 %s 个文件 (%s 修改 + %s 新增)。",
            len(to_index),
            len(modified_paths),
            len(new_paths),
        )

        # Phase A: 删除修改文件的旧索引 chunks（先删后读，避免索引残留）
        for fp in to_index:
            if fp in db_state:
                _delete_chunks(collection, fp, sparse_writer)

        # Phase B: 并行读取所有文件并构建 Document
        reporter.update_phase("并行读取文件")
        all_docs: dict[str, list] = {}

        def _read_one(fp: str):
            mtime, stype = disk_all[fp]
            return build_documents_for_path_cached(fp, mtime, stype, conn=None)

        cpu = os.cpu_count() or 4
        max_workers = min(max(4, cpu - 1), len(to_index))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_read_one, fp): fp for fp in to_index}
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    all_docs[fp] = future.result()
                except Exception:
                    all_docs[fp] = []

        # Phase C: 串行写入索引 (Embedding API + Sparse + 状态更新)
        reporter.update_phase("写入索引")
        for i, fp in enumerate(to_index):
            mtime, stype = disk_all[fp]
            docs = all_docs[fp]

            # 写回扫描缓存
            if scan_cache_conn and docs:
                _save_cached_docs(scan_cache_conn, fp, mtime, stype, docs, auto_commit=False)

            if docs:
                file_estimated_tokens = estimate_tokens_from_texts([doc.page_content for doc in docs])
                ok = False
                for attempt in range(3):
                    try:
                        vectordb.add_documents(docs)
                        ok = True
                        embedding_stats = embeddings.stats_snapshot()
                        reporter.set_embedding_stats(
                            embedding_stats.cache_hit_text_count,
                            embedding_stats.uncached_text_count,
                            embedding_stats.remote_batch_count,
                        )
                        reporter.add_dense_chunks(len(docs))
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(3)
                        else:
                            logger.error("索引失败 %s: %s", os.path.basename(fp), e)
                if not ok:
                    reporter.add_failed_file()
                    continue

                # Write to FTS5 Sparse Index
                file_id = generate_file_id(fp)
                file_counters = {}
                chunks_to_write = []
                for doc in docs:
                    meta = doc.metadata.copy()
                    chunk_type = meta.get("chunk_type", "content")
                    if chunk_type == "content":
                        chunk_idx = meta.get("chunk_idx", 0)
                        chunk_suffix = f"c{chunk_idx}"
                    elif chunk_type == "filename":
                        chunk_suffix = "fn"
                    elif chunk_type == "heading":
                        count = file_counters.get(f"{file_id}_heading", 0)
                        chunk_suffix = f"h{count}"
                        file_counters[f"{file_id}_heading"] = count + 1
                    else:
                        count = file_counters.get(f"{file_id}_{chunk_type}", 0)
                        chunk_suffix = f"x{count}"
                        file_counters[f"{file_id}_{chunk_type}"] = count + 1

                    chunk_id = f"{file_id}_{chunk_suffix}"
                    filename = meta.pop("filename", "")
                    filetype = meta.pop("type", "")
                    title_path_list = meta.pop("title_path", [])
                    title_path = tuple(title_path_list) if title_path_list else ()
                    meta.pop("chunk_type", None)
                    doc_mtime = float(meta.pop("mtime", 0.0))
                    ctime = float(meta.pop("ctime", 0.0))
                    meta.pop("source", None)
                    meta.pop("source_type", None)

                    indexed_chunk = IndexedChunk(
                        chunk_id=chunk_id,
                        file_id=file_id,
                        filepath=fp,
                        filename=filename,
                        source_type=stype,
                        filetype=filetype,
                        chunk_type=chunk_type,
                        title_path=title_path,
                        content=doc.page_content,
                        embedding_text=doc.page_content,
                        sparse_text=doc.page_content,
                        chunk_index=meta.get("chunk_idx", 0),
                        mtime=doc_mtime,
                        ctime=ctime,
                        metadata=meta
                    )
                    chunks_to_write.append(indexed_chunk)

                if chunks_to_write:
                    try:
                        sparse_writer.upsert_chunks(chunks_to_write)
                        reporter.add_sparse_chunks(len(chunks_to_write))
                    except Exception as e:
                        logger.error("写入 Sparse 索引失败 %s: %s", os.path.basename(fp), e)
                        reporter.add_failed_file()
                reporter.add_processed_file(len(docs), file_estimated_tokens)
            else:
                reporter.add_skipped_file()

            conn.execute(
                "INSERT OR REPLACE INTO file_index (filepath, mtime, source_type, indexed_at) VALUES (?, ?, ?, ?)",
                (fp, mtime, stype, time.time()),
            )

            if (i + 1) % 20 == 0 or i == len(to_index) - 1:
                conn.commit()
                pct = (i + 1) / len(to_index) * 100
                print(f"  进度: {pct:.0f}% ({i+1}/{len(to_index)})")
                logger.info("增量索引进度: %.0f%% (%s/%s)", pct, i + 1, len(to_index))

        conn.commit()

    if scan_cache_conn:
        scan_cache_conn.close()
    conn.close()
    elapsed = time.time() - total_start

    logger.info("增量索引完成。新增=%s, 修改=%s, 删除=%s", len(new_paths), len(modified_paths), len(deleted_paths))
    logger.info("嵌入缓存: %s", embeddings.stats_str())
    logger.info("总耗时: %.1fs", elapsed)
    reporter.finish()

def _rebuild_state_db():
    """Rebuild the state DB after a full index by scanning disk state."""
    conn = sqlite3.connect(get_settings().index_state_db)
    _init_state_db(conn)
    conn.execute("DELETE FROM file_index")

    disk_files = _scan_disk_files()
    disk_mweb = _scan_disk_mweb()
    now = time.time()

    for fp, (mtime, stype) in {**disk_files, **disk_mweb}.items():
        conn.execute(
            "INSERT OR REPLACE INTO file_index (filepath, mtime, source_type, indexed_at) VALUES (?, ?, ?, ?)",
            (fp, mtime, stype, now),
        )
    conn.commit()
    conn.close()
    print(f"状态数据库已重建: {len(disk_files)} 文件 + {len(disk_mweb)} 笔记")
    logger.info("状态数据库已重建: %s 文件 + %s 笔记", len(disk_files), len(disk_mweb))


def run_full():
    """Full rebuild: use pipeline_indexer then rebuild state DB."""
    try:
        from everythingsearch.indexing.pipeline_indexer import build_pipeline_index
        build_pipeline_index()
        _rebuild_state_db()
    except KeyboardInterrupt:
        print("\n用户中断，索引已停止。")
        logger.info("用户中断索引操作。")
        sys.exit(1)


if __name__ == "__main__":
    try:
        setup_cli_logging()
        parser = argparse.ArgumentParser(description="增量/全量索引")
        parser.add_argument("--full", action="store_true", help="执行完整重建（而非增量更新）")
        args = parser.parse_args()

        if args.full:
            run_full()
        else:
            run_incremental()
    except KeyboardInterrupt:
        print("\n用户中断，已退出。")
        sys.exit(1)
