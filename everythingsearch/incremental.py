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
# 直接执行脚本时补上仓库根目录，保证绝对包导入可用。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from everythingsearch.indexing.document_scan import (
    FILE_READ_TIMEOUT,
    _init_scan_cache,
    _save_cached_docs,
    build_documents_for_path_cached,
)
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
from everythingsearch.indexing.chunk_conversion import docs_to_indexed_chunks, generate_file_id
from everythingsearch.indexing.full_rebuild_plan import FullRebuildPlan, add_full_rebuild_arguments
from everythingsearch.indexing.full_rebuild_environment import (
    prepare_full_rebuild_environment,
    print_full_rebuild_summary,
)
from everythingsearch.infra.app_service_control import (
    restart_search_service,
    suspend_search_service_for_rebuild,
)
from everythingsearch.infra.index_run_lock import IndexRunLock, read_index_run_lock_holder
from everythingsearch.indexing.sparse_index_writer import SQLiteSparseIndexWriter
from everythingsearch.indexing.dense_index_writer import ChromaDenseIndexWriter
from everythingsearch.retrieval.embedding import DashScopeEmbeddingProvider
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


def _load_db_state(conn: sqlite3.Connection) -> dict[str, tuple[float, str]]:
    """Load all tracked files from the state database."""
    rows = conn.execute("SELECT filepath, mtime, source_type FROM file_index").fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def _delete_chunks(collection, filepath: str, sparse_writer: SQLiteSparseIndexWriter = None):
    """Delete all ChromaDB and FTS5 chunks belonging to a file."""
    file_id = generate_file_id(filepath)
    try:
        collection.delete(where={"file_id": file_id})
    except Exception as exc:
        raise RuntimeError(f"删除 Dense 索引失败: {filepath}") from exc
    
    if sparse_writer:
        try:
            # Assuming sparse_writer has a delete_file_by_path or similar method
            # Since we only have file_id in pipeline_indexer, let's generate it
            sparse_writer.delete_file(file_id)
        except Exception as e:
            logger.warning(f"删除 Sparse 索引失败 {filepath}: {e}")


def _reload_app_service_after_indexing() -> None:
    """索引写入完成后重启搜索服务，加载最新 sparse / chroma 数据。"""
    settings = get_settings()
    try:
        started = restart_search_service(settings.port)
    except RuntimeError as exc:
        logger.error("索引已完成，但重启搜索服务失败: %s", exc)
        sys.exit(1)
    if not started:
        logger.warning(
            "索引已完成。搜索服务未自动启动，请执行: ./scripts/run_app.sh start"
        )


def run_incremental():
    settings = get_settings()
    lock = IndexRunLock(settings.index_run_lock_path, "incremental")
    if not lock.try_acquire():
        holder = read_index_run_lock_holder(settings.index_run_lock_path)
        if holder is not None:
            logger.warning(
                "已有索引任务正在运行 (pid=%s, mode=%s)，本次增量更新跳过。",
                holder.pid,
                holder.run_mode,
            )
        else:
            logger.warning("已有索引任务正在运行，本次增量更新跳过。")
        return
    try:
        _run_incremental_impl()
    except KeyboardInterrupt:
        logger.warning("用户中断，索引已停止。")
        sys.exit(1)
    finally:
        lock.release()


def _run_incremental_impl():
    settings = get_settings()
    require_target_dirs(settings)
    require_dashscope_api_key(settings)
    apply_sdk_environment(settings)
    db_path = settings.index_state_db
    total_start = time.time()

    if settings.enable_mweb and settings.mweb_export_script and os.path.isfile(settings.mweb_export_script):
        logger.info("正在运行 MWeb 导出...")
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

    logger.info("正在扫描文件系统...")
    disk_files = scan_disk_files_for_index()
    disk_mweb = scan_mweb_notes_for_index()
    logger.info("扫描到文件数: %s, MWeb 笔记数: %s", len(disk_files), len(disk_mweb))
    logger.info("  文件: %s  笔记: %s", len(disk_files), len(disk_mweb))

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
    logger.info(
        "变更: +%s ~%s -%s  (新增/修改/删除)",
        len(new_paths),
        len(modified_paths),
        len(deleted_paths),
    )

    if not new_paths and not modified_paths and not deleted_paths:
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

        fallback_plan = FullRebuildPlan.keep_caches_for_fallback()
        with suspend_search_service_for_rebuild(settings.port):
            prepare_full_rebuild_environment(settings, fallback_plan)
            if build_pipeline_index(
                initial_scale_snapshot=scale_snapshot,
                transition_reason="Dense collection 不存在",
                full_rebuild_plan=fallback_plan,
            ):
                _rebuild_state_db()
            else:
                logger.error("全量索引构建未完成，跳过状态库重建。")
                sys.exit(1)
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

    dense_embedding_provider = DashScopeEmbeddingProvider(settings)
    dense_writer = ChromaDenseIndexWriter(settings, dense_embedding_provider)

    sparse_writer = SQLiteSparseIndexWriter(settings)

    if deleted_paths:
        reporter.update_phase("删除已移除文件索引")
        logger.info("正在删除 %s 个已移除文件的索引...", len(deleted_paths))
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
            from everythingsearch.indexing.document_scan import _init_scan_cache
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
            from everythingsearch.indexing.document_scan import _init_scan_cache
            _init_scan_cache(scan_cache_conn)
        logger.info(
            "正在索引 %s 个文件 (%s 修改 + %s 新增)...",
            len(to_index),
            len(modified_paths),
            len(new_paths),
        )

        # Phase A: 删除修改文件的旧索引 chunks（先删后读，避免索引残留）
        for fp in to_index:
            if fp in db_state:
                _delete_chunks(collection, fp, sparse_writer)

        # Phase B: 并行读取所有文件并构建 Document
        all_docs: dict[str, list] = {}

        def _read_one(fp: str):
            mtime, stype = disk_all[fp]
            return build_documents_for_path_cached(fp, mtime, stype, conn=None)

        cpu = os.cpu_count() or 4
        max_workers = min(max(4, cpu - 1), len(to_index))
        with reporter.blocking_phase("并行扫描文件"):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_read_one, fp): fp for fp in to_index}
                for future in as_completed(futures):
                    fp = futures[future]
                    try:
                        docs = future.result(timeout=FILE_READ_TIMEOUT * 2) or []
                        all_docs[fp] = docs
                    except Exception:
                        docs = []
                        all_docs[fp] = docs
                    reporter.add_scanned_file(len(docs), 0)

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
                source_type = docs[0].metadata.get("source_type", stype)
                chunks_to_write = docs_to_indexed_chunks(fp, source_type, docs)
                ok = False
                for attempt in range(3):
                    try:
                        dense_writer.upsert_chunks(chunks_to_write)
                        ok = True
                        embedding_stats = dense_embedding_provider.stats_snapshot()
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

                sparse_ok = True
                if chunks_to_write:
                    try:
                        sparse_writer.upsert_chunks(chunks_to_write)
                        reporter.add_sparse_chunks(len(chunks_to_write))
                    except Exception as e:
                        logger.error("写入 Sparse 索引失败 %s: %s", os.path.basename(fp), e)
                        sparse_ok = False
                        try:
                            dense_writer.delete_file(chunks_to_write[0].file_id)
                        except Exception as rollback_exc:
                            logger.error(
                                "Sparse 失败，回滚 Dense 索引失败 %s: %s",
                                os.path.basename(fp),
                                rollback_exc,
                            )

                if not sparse_ok:
                    reporter.add_failed_file()
                    continue

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
                logger.info("  进度: %.0f%% (%s/%s)", pct, i + 1, len(to_index))

        conn.commit()

    if scan_cache_conn:
        scan_cache_conn.close()
    conn.close()
    elapsed = time.time() - total_start

    logger.info("增量索引完成。新增=%s, 修改=%s, 删除=%s", len(new_paths), len(modified_paths), len(deleted_paths))
    # 统计字符串保持与旧日志兼容
    embed_snapshot = dense_embedding_provider.stats_snapshot()
    total_embed = embed_snapshot.cache_hit_text_count + embed_snapshot.uncached_text_count
    if total_embed == 0:
        logger.info("嵌入缓存: 无嵌入调用")
    else:
        logger.info(
            "嵌入缓存: 远端文本: %s / %s (%s 缓存命中, %s 批次)",
            embed_snapshot.uncached_text_count,
            total_embed,
            embed_snapshot.cache_hit_text_count,
            embed_snapshot.remote_batch_count,
        )
    logger.info("总耗时: %.1fs", elapsed)
    reporter.finish()
    _reload_app_service_after_indexing()


def _rebuild_state_db():
    """Rebuild the state DB after a full index by scanning disk state."""
    conn = sqlite3.connect(get_settings().index_state_db)
    _init_state_db(conn)
    conn.execute("DELETE FROM file_index")

    disk_files = scan_disk_files_for_index()
    disk_mweb = scan_mweb_notes_for_index()
    now = time.time()

    for fp, (mtime, stype) in {**disk_files, **disk_mweb}.items():
        conn.execute(
            "INSERT OR REPLACE INTO file_index (filepath, mtime, source_type, indexed_at) VALUES (?, ?, ?, ?)",
            (fp, mtime, stype, now),
        )
    conn.commit()
    conn.close()
    logger.info("状态数据库已重建: %s 文件 + %s 笔记", len(disk_files), len(disk_mweb))


def run_full(plan: FullRebuildPlan):
    """Full rebuild: use pipeline_indexer then rebuild state DB."""
    settings = get_settings()
    require_target_dirs(settings)
    require_dashscope_api_key(settings)
    apply_sdk_environment(settings)

    if plan.dry_run:
        print_full_rebuild_summary(settings, plan)
        return

    lock = IndexRunLock(settings.index_run_lock_path, "full")
    if not lock.try_acquire():
        holder = read_index_run_lock_holder(settings.index_run_lock_path)
        if holder is not None:
            logger.error(
                "已有索引任务正在运行 (pid=%s, mode=%s)，无法开始全量重建。",
                holder.pid,
                holder.run_mode,
            )
        else:
            logger.error("已有索引任务正在运行，无法开始全量重建。")
        sys.exit(1)

    try:
        with suspend_search_service_for_rebuild(settings.port):
            _run_full_rebuild_body(settings, plan)
        _reload_app_service_after_indexing()
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("用户中断，索引已停止。")
        sys.exit(1)
    finally:
        lock.release()


def _run_full_rebuild_body(settings, plan: FullRebuildPlan) -> None:
    if not plan.resume:
        prepare_full_rebuild_environment(settings, plan)

    from everythingsearch.indexing.pipeline_indexer import build_pipeline_index

    if build_pipeline_index(full_rebuild_plan=plan):
        _rebuild_state_db()
    else:
        logger.error("全量索引构建未完成，跳过状态库重建。")
        sys.exit(1)


if __name__ == "__main__":
    try:
        setup_cli_logging(
            also_write_incremental_daily=True,
            stream_progress_to_tty=sys.stdout.isatty(),
        )
        parser = argparse.ArgumentParser(description="增量/全量索引")
        parser.add_argument("--full", action="store_true", help="执行完整重建（而非增量更新）")
        add_full_rebuild_arguments(parser)
        args = parser.parse_args()

        if args.full:
            run_full(FullRebuildPlan.from_namespace(args))
        else:
            run_incremental()
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("用户中断，已退出。")
        sys.exit(1)
