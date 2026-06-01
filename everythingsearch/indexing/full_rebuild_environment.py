"""全量重建前的环境清理与启动摘要。"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.full_rebuild_plan import FullRebuildPlan

logger = logging.getLogger(__name__)


def _sqlite_sidecars(db_path: Path) -> list[Path]:
    return [db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")]


def _paths_for_plan(settings: Settings, plan: FullRebuildPlan) -> tuple[list[Path], list[Path]]:
    """返回 (将删除, 将保留) 的路径列表。"""
    to_remove: list[Path] = []
    to_keep: list[Path] = []

    derived = [
        Path(settings.sparse_index_path),
        Path(settings.index_state_db),
        Path(settings.rebuild_staging_path),
        Path(settings.rebuild_checkpoint_path),
        Path(settings.persist_directory),
    ]
    for path in derived:
        to_remove.append(path)

    embedding = Path(settings.embedding_cache_path)
    scan = Path(settings.scan_cache_path)

    if plan.keep_embedding_cache:
        to_keep.append(embedding)
    else:
        to_remove.append(embedding)

    if plan.keep_scan_cache:
        to_keep.append(scan)
    else:
        to_remove.append(scan)

    return to_remove, to_keep


def print_full_rebuild_summary(settings: Settings, plan: FullRebuildPlan) -> None:
    """打印全量重建启动摘要。"""
    to_remove, to_keep = _paths_for_plan(settings, plan)

    if plan.resume:
        mode = "断点续跑"
    elif plan.keep_embedding_cache and plan.keep_scan_cache:
        mode = "保留 embedding + scan 缓存"
    elif plan.keep_embedding_cache:
        mode = "保留 embedding 缓存"
    elif plan.keep_scan_cache:
        mode = "保留 scan 解析缓存"
    else:
        mode = "干净重建（默认）"

    logger.info("全量重建模式: %s", mode)
    if plan.dry_run:
        logger.info("（dry-run：仅预览，不删除、不写入）")

    if to_remove:
        logger.info("将删除:")
        for path in to_remove:
            logger.info("  - %s", path)

    if to_keep:
        logger.info("将保留:")
        for path in to_keep:
            logger.info("  - %s", path)

    if not plan.keep_embedding_cache and not plan.resume and not plan.dry_run:
        logger.info("提示: 保留缓存请加 --keep-embedding-cache / --keep-scan-cache / --keep-caches")


def _unlink_sqlite(path: Path) -> int:
    """删除 SQLite 主库及 -wal/-shm 附属文件，返回释放的字节数。"""
    freed = 0
    for candidate in _sqlite_sidecars(path):
        if candidate.is_file():
            try:
                freed += candidate.stat().st_size
            except OSError:
                pass
            candidate.unlink()
    return freed


def cleanup_rebuild_artifacts(settings: Settings) -> int:
    """全量重建成功后删除 staging / checkpoint 临时库，释放磁盘空间。"""
    paths = [
        Path(settings.rebuild_staging_path),
        Path(settings.rebuild_checkpoint_path),
    ]
    freed = 0
    removed: list[str] = []
    for path in paths:
        nbytes = _unlink_sqlite(path)
        if nbytes > 0:
            freed += nbytes
            removed.append(str(path))
    if removed:
        logger.info(
            "已清理全量重建临时文件 (%d 个): %s，释放约 %.2f MB",
            len(removed),
            ", ".join(removed),
            freed / (1024 * 1024),
        )
    return freed


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        _unlink_sqlite(path)
    elif path.suffix == ".db":
        _unlink_sqlite(path)


def prepare_full_rebuild_environment(settings: Settings, plan: FullRebuildPlan) -> None:
    """按计划在全量重建开始前清理环境（resume 时不调用）。"""
    print_full_rebuild_summary(settings, plan)
    if plan.dry_run:
        return

    to_remove, _ = _paths_for_plan(settings, plan)
    for path in to_remove:
        if path == Path(settings.persist_directory):
            shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True, exist_ok=True)
            logger.info("已清理 Dense 目录: %s", path)
            continue
        if path.suffix == ".db" or str(path).endswith(".db"):
            if path.is_file() or path.with_suffix(".db-wal").exists():
                _unlink_sqlite(path)
                logger.info("已删除: %s", path)
            continue
        _remove_path(path)
