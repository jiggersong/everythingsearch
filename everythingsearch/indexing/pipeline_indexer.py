"""独立全量索引器（专供 Pipeline 双写使用）。"""

import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document
from pathlib import Path
from everythingsearch.infra.settings import get_settings, require_dashscope_api_key, require_target_dirs, apply_sdk_environment
from everythingsearch.logging_config import setup_cli_logging
from everythingsearch.indexing.document_scan import scan_files, scan_mweb_notes
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.dense_index_writer import ChromaDenseIndexWriter
from everythingsearch.indexing.dense_lifecycle import reset_dense_collection
from everythingsearch.indexing.file_scanner import (
    scan_disk_files_for_index,
    scan_mweb_notes_for_index,
)
from everythingsearch.indexing.chunk_conversion import docs_to_indexed_chunks, generate_file_id
from everythingsearch.indexing.full_rebuild_environment import (
    cleanup_rebuild_artifacts,
    print_full_rebuild_summary,
)
from everythingsearch.indexing.full_rebuild_plan import FullRebuildPlan
from everythingsearch.indexing.rebuild_checkpoint import (
    PHASE_DENSE,
    PHASE_SPARSE,
    RebuildCheckpointStore,
    compute_rebuild_config_fingerprint,
)
from everythingsearch.indexing.rebuild_staging import RebuildStagingStore
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
from everythingsearch.indexing.sparse_index_writer import (
    PreparedSparseRecords,
    SQLiteSparseIndexWriter,
    resolve_sparse_tokenize_workers,
)
from everythingsearch.retrieval.embedding import DashScopeEmbeddingProvider

logger = logging.getLogger(__name__)

MAX_DENSE_INDEX_BATCH_SIZE = 50


def _calculate_dense_batch_size(configured_batch_size: int) -> int:
    return max(1, min(configured_batch_size, MAX_DENSE_INDEX_BATCH_SIZE))


def _scan_and_convert_chunks(
    settings,
    reporter: IndexProgressReporter,
) -> list[IndexedChunk]:
    logger.info("正在扫描本地文件...")
    docs, _ = scan_files(progress_reporter=reporter)
    logger.info("正在扫描 MWeb 笔记...")
    mweb_docs, _ = scan_mweb_notes(progress_reporter=reporter)
    docs.extend(mweb_docs)
    if not docs:
        return []

    logger.info("扫描完成，共 %s 个 chunk。", len(docs))
    reporter.scanning_complete()

    groups: dict[str, list[Document]] = defaultdict(list)
    for doc in docs:
        filepath = doc.metadata.get("source", "")
        groups[filepath].append(doc)

    def _convert_group(filepath: str, group_docs: list[Document]) -> list[IndexedChunk]:
        source_type = group_docs[0].metadata.get("source_type", "file") if group_docs else "file"
        return docs_to_indexed_chunks(filepath, source_type, group_docs, settings=settings)

    chunks_to_write: list[IndexedChunk] = []
    cpu = os.cpu_count() or 4
    max_workers = min(max(4, cpu - 1), max(1, len(groups)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_convert_group, fp, grp): fp for fp, grp in groups.items()}
        for future in as_completed(futures):
            try:
                chunks_to_write.extend(future.result())
            except Exception:
                logger.exception("转换文件 chunk 失败")
    return chunks_to_write


def _prepare_sparse_batch_parallel(
    writer: SQLiteSparseIndexWriter,
    batch: list[IndexedChunk],
    max_workers: int,
) -> PreparedSparseRecords:
    if len(batch) <= 64 or max_workers <= 1:
        return writer.prepare_batch(batch)

    chunk_size = max(1, (len(batch) + max_workers - 1) // max_workers)
    parts = [batch[i : i + chunk_size] for i in range(0, len(batch), chunk_size)]
    prepared_parts: list[PreparedSparseRecords] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(parts))) as executor:
        futures = [executor.submit(writer.prepare_batch, part) for part in parts]
        for future in as_completed(futures):
            prepared_parts.append(future.result())
    return PreparedSparseRecords.merge(prepared_parts)


def _write_sparse_batches(
    *,
    settings,
    sparse_writer: SQLiteSparseIndexWriter,
    chunks_to_write: list[IndexedChunk],
    sparse_batch_start: int,
    batch_size: int,
    checkpoint_interval: int,
    skip_fts_delete_on_fresh: bool,
    skip_optimize: bool,
    checkpoint_store: RebuildCheckpointStore,
    run_id: str,
    config_fingerprint: str,
    reporter: IndexProgressReporter,
) -> bool:
    total_chunks = len(chunks_to_write)
    tokenize_workers = resolve_sparse_tokenize_workers(settings)
    last_checkpoint_at = sparse_batch_start
    last_progress_log = time.time()

    skip_fts_delete = skip_fts_delete_on_fresh and sparse_batch_start == 0
    with sparse_writer.open_bulk_session(skip_fts_delete=skip_fts_delete) as session:
        for i in range(sparse_batch_start, total_chunks, batch_size):
            batch = chunks_to_write[i : i + batch_size]
            prepared = _prepare_sparse_batch_parallel(sparse_writer, batch, tokenize_workers)
            session.write_prepared(prepared)
            reporter.add_sparse_chunks(len(batch))
            batch_end = i + len(batch)

            if batch_end - last_checkpoint_at >= checkpoint_interval or batch_end == total_chunks:
                checkpoint_store.save(
                    run_id=run_id,
                    config_fingerprint=config_fingerprint,
                    phase=PHASE_SPARSE,
                    sparse_batch_end=batch_end,
                    dense_batch_end=0,
                    total_chunks=total_chunks,
                )
                last_checkpoint_at = batch_end

            now = time.time()
            if now - last_progress_log >= 30.0 or batch_end == total_chunks:
                logger.info("已写入 Sparse: %d / %d", batch_end, total_chunks)
                last_progress_log = now

    if skip_optimize:
        logger.info("已跳过 Sparse Index optimize（--skip-sparse-optimize）。")
    else:
        logger.info("Sparse Index 写入完成，开始 optimize。")
        with reporter.blocking_phase("Sparse Index optimize"):
            sparse_writer.optimize()
    return True


def build_pipeline_index(
    initial_scale_snapshot: IndexScaleSnapshot | None = None,
    transition_reason: str | None = None,
    full_rebuild_plan: FullRebuildPlan | None = None,
) -> bool:
    """构建专属于新版 Pipeline 的底层索引。"""
    settings = get_settings()
    require_target_dirs(settings)
    require_dashscope_api_key(settings)
    apply_sdk_environment(settings)

    if full_rebuild_plan and full_rebuild_plan.dry_run:
        print_full_rebuild_summary(settings, full_rebuild_plan)
        return True

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

    checkpoint_store = RebuildCheckpointStore(settings.rebuild_checkpoint_path)
    staging_store = RebuildStagingStore(settings.rebuild_staging_path)
    config_fingerprint = compute_rebuild_config_fingerprint(settings)

    resume = None
    if full_rebuild_plan and full_rebuild_plan.resume:
        resume = checkpoint_store.is_resumable(settings)
        if resume is None:
            logger.error("无可续跑断点（checkpoint 缺失或与当前配置不匹配），请去掉 --resume 执行干净全量。")
            reporter.finish()
            return False
    elif full_rebuild_plan is None:
        resume = checkpoint_store.is_resumable(settings)

    run_id = resume.run_id if resume else uuid.uuid4().hex[:12]
    chunks_to_write: list[IndexedChunk] = []
    sparse_batch_start = 0
    dense_batch_start = 0

    if resume is not None:
        logger.info(
            "检测到可续跑断点: phase=%s sparse_end=%s dense_end=%s total=%s",
            resume.phase,
            resume.sparse_batch_end,
            resume.dense_batch_end,
            resume.total_chunks,
        )
        chunks_to_write = staging_store.load_chunks()
        if not chunks_to_write:
            if full_rebuild_plan and full_rebuild_plan.resume:
                logger.error(
                    "断点存在但 staging 为空，无法续跑。请去掉 --resume 执行干净全量。"
                )
                reporter.finish()
                return False
            logger.warning("断点存在但 staging 为空，将重新扫描。")
            resume = None
        else:
            sparse_batch_start = resume.sparse_batch_end
            dense_batch_start = resume.dense_batch_end

    if resume is None:
        checkpoint_store.clear()
        staging_store.clear()
        if full_rebuild_plan is None:
            sparse_db_path = Path(settings.sparse_index_path)
            if sparse_db_path.exists():
                sparse_db_path.unlink()
                logger.info("已删除旧的 Sparse DB: %s", sparse_db_path)
            reset_dense_collection(settings.persist_directory)

        reporter.update_phase("扫描与解析文件")
        chunks_to_write = _scan_and_convert_chunks(settings, reporter)
        if not chunks_to_write:
            logger.warning("未扫描到任何文档内容，将创建空索引。")
            cleanup_rebuild_artifacts(settings)
            SQLiteSparseIndexWriter(settings)
            reset_dense_collection(settings.persist_directory)
            reporter.finish()
            return True

        refined_estimate = estimate_cost_from_chunks(chunks_to_write)
        reporter.update_estimate(refined_estimate)
        staging_store.save_chunks(chunks_to_write)
        checkpoint_store.save(
            run_id=run_id,
            config_fingerprint=config_fingerprint,
            phase=PHASE_SPARSE,
            sparse_batch_end=0,
            dense_batch_end=0,
            total_chunks=len(chunks_to_write),
        )
    else:
        refined_estimate = estimate_cost_from_chunks(chunks_to_write)
        reporter.update_estimate(refined_estimate)

    total_chunks = len(chunks_to_write)
    sparse_batch_size = settings.sparse_index_batch_size
    sparse_checkpoint_interval = settings.sparse_checkpoint_interval
    sparse_writer = SQLiteSparseIndexWriter(settings)
    embedding_provider = DashScopeEmbeddingProvider(settings)
    dense_writer = ChromaDenseIndexWriter(settings, embedding_provider)
    skip_sparse_optimize = bool(full_rebuild_plan and full_rebuild_plan.skip_sparse_optimize)

    if resume is None or resume.phase == PHASE_SPARSE:
        if resume is None or sparse_batch_start == 0:
            sparse_db_path = Path(settings.sparse_index_path)
            if sparse_db_path.exists() and sparse_batch_start == 0 and resume is not None:
                sparse_db_path.unlink()
                logger.info("续跑前清理不完整 Sparse DB: %s", sparse_db_path)

        logger.info("开始双写索引 (Sparse + Dense)...")
        try:
            reporter.update_phase("Sparse Index 写入")
            logger.info(
                "写入 Sparse Index (batch=%d, checkpoint_interval=%d)。",
                sparse_batch_size,
                sparse_checkpoint_interval,
            )
            _write_sparse_batches(
                settings=settings,
                sparse_writer=sparse_writer,
                chunks_to_write=chunks_to_write,
                sparse_batch_start=sparse_batch_start,
                batch_size=sparse_batch_size,
                checkpoint_interval=sparse_checkpoint_interval,
                skip_fts_delete_on_fresh=settings.sparse_skip_fts_delete_on_fresh,
                skip_optimize=skip_sparse_optimize,
                checkpoint_store=checkpoint_store,
                run_id=run_id,
                config_fingerprint=config_fingerprint,
                reporter=reporter,
            )
            checkpoint_store.save(
                run_id=run_id,
                config_fingerprint=config_fingerprint,
                phase=PHASE_DENSE,
                sparse_batch_end=total_chunks,
                dense_batch_end=0,
                total_chunks=total_chunks,
            )
        except Exception as exc:
            logger.error("Sparse 索引构建失败: %s", exc)
            reporter.finish()
            return False
    elif resume.phase == PHASE_DENSE:
        dense_batch_start = resume.dense_batch_end
        if dense_batch_start == 0:
            reset_dense_collection(settings.persist_directory)

    try:
        reporter.update_phase("Dense Index 写入")
        logger.info("写入 Dense 索引 (调用 Embedding API，请耐心等待)...")
        dense_batch_size = _calculate_dense_batch_size(settings.indexer_batch_size)
        logger.info("Dense Index 外层批大小: %d", dense_batch_size)
        dense_checkpoint_interval = sparse_checkpoint_interval
        last_dense_checkpoint = dense_batch_start
        with reporter.blocking_phase("Dense Index 写入"):
            for i in range(dense_batch_start, total_chunks, dense_batch_size):
                batch = chunks_to_write[i : i + dense_batch_size]
                dense_writer.upsert_chunks(batch)
                reporter.add_dense_chunks(len(batch))
                embedding_stats = embedding_provider.stats_snapshot()
                reporter.set_embedding_stats(
                    embedding_stats.cache_hit_text_count,
                    embedding_stats.uncached_text_count,
                    embedding_stats.remote_batch_count,
                )
                batch_end = i + len(batch)
                if batch_end - last_dense_checkpoint >= dense_checkpoint_interval or batch_end == total_chunks:
                    checkpoint_store.save(
                        run_id=run_id,
                        config_fingerprint=config_fingerprint,
                        phase=PHASE_DENSE,
                        sparse_batch_end=total_chunks,
                        dense_batch_end=batch_end,
                        total_chunks=total_chunks,
                    )
                    last_dense_checkpoint = batch_end
                logger.info("已写入 Dense Batch: %d / %d", batch_end, total_chunks)
        logger.info("Dense Index 写入完成。")
    except Exception as exc:
        logger.error("Dense 索引构建失败: %s", exc)
        reporter.finish()
        return False

    cleanup_rebuild_artifacts(settings)

    duration = time.time() - total_start
    logger.info("Pipeline 索引全量构建完成！总耗时: %.2f 秒", duration)
    reporter.finish()
    return True


if __name__ == "__main__":
    try:
        setup_cli_logging(stream_progress_to_tty=sys.stdout.isatty())
        ok = build_pipeline_index()
        if not ok:
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("用户中断，索引已停止。")
        sys.exit(1)
