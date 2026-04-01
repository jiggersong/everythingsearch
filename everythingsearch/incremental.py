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
import unicodedata
import logging

# 直接执行 `python everythingsearch/incremental.py` 时，sys.path 里只有包目录；
# 这里补上仓库根目录，保证绝对包导入和 legacy config 兼容加载都可用。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from everythingsearch.indexer import (
    normalize_path,
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


def _scan_disk_files() -> dict[str, tuple[float, str]]:
    """Scan TARGET_DIR(s) and return {filepath: (mtime, 'file')}."""
    settings = get_settings()
    result = {}
    for target_dir in require_target_dirs(settings):
        if not os.path.isdir(target_dir):
            continue
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.startswith('.'):
                    continue
                _, ext = os.path.splitext(f)
                ext = ext.lower()
                if ext not in settings.supported_extensions:
                    continue
                raw_path = os.path.join(root, f)
                filepath = normalize_path(raw_path)
                if settings.index_only_keywords:
                    if not any(kw in filepath for kw in settings.index_only_keywords):
                        continue
                try:
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue
                result[filepath] = (mtime, "file")
    return result


def _scan_disk_mweb() -> dict[str, tuple[float, str]]:
    """Scan MWEB_DIR and return {filepath: (mtime, 'mweb')}."""
    settings = get_settings()
    result = {}
    if not settings.enable_mweb:
        return result
    mweb_dir = settings.mweb_dir
    if not mweb_dir or not os.path.isdir(mweb_dir):
        return result
    for root, dirs, files in os.walk(mweb_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if not f.endswith('.md') or f.startswith('.'):
                continue
            raw_path = os.path.join(root, f)
            filepath = normalize_path(raw_path)
            try:
                mtime = os.path.getmtime(filepath)
            except OSError:
                continue
            result[filepath] = (mtime, "mweb")
    return result


def _load_db_state(conn: sqlite3.Connection) -> dict[str, tuple[float, str]]:
    """Load all tracked files from the state database."""
    rows = conn.execute("SELECT filepath, mtime, source_type FROM file_index").fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def _delete_chunks(collection, filepath: str):
    """Delete all ChromaDB chunks belonging to a file."""
    try:
        collection.delete(where={"source": filepath})
    except Exception:
        pass


def run_incremental():
    settings = get_settings()
    require_target_dirs(settings)
    require_dashscope_api_key(settings)
    apply_sdk_environment(settings)
    db_path = settings.index_state_db
    total_start = time.time()

    logger.info("增量索引开始。")

    if settings.enable_mweb and settings.mweb_export_script and os.path.isfile(settings.mweb_export_script):
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

    logger.info("开始扫描文件系统。")
    disk_files = _scan_disk_files()
    logger.info("扫描到文件数: %s", len(disk_files))

    disk_mweb = _scan_disk_mweb()
    logger.info("扫描到 MWeb 笔记数: %s", len(disk_mweb))

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

    logger.info("变更统计开始。")
    logger.info("新增: %s", len(new_paths))
    logger.info("修改: %s", len(modified_paths))
    logger.info("删除: %s", len(deleted_paths))

    if not new_paths and not modified_paths and not deleted_paths:
        logger.info("索引已是最新，无需更新。")
        conn.close()
        return

    client = chromadb.PersistentClient(path=settings.persist_directory)
    existing_collections = [c.name for c in client.list_collections()]

    if "local_files" not in existing_collections:
        logger.warning("ChromaDB collection 不存在，将执行完整索引。")
        conn.close()
        from everythingsearch.indexer import build_index
        build_index()
        _rebuild_state_db()
        return

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

    if deleted_paths:
        logger.info("开始删除 %s 个已移除文件的索引。", len(deleted_paths))
        for fp in deleted_paths:
            _delete_chunks(collection, fp)
            conn.execute("DELETE FROM file_index WHERE filepath = ?", (fp,))
        conn.commit()
        # 同步清理扫描缓存，避免缓存膨胀
        cache_path = settings.scan_cache_path
        if cache_path:
            from everythingsearch.indexer import _init_scan_cache
            scan_conn = sqlite3.connect(cache_path)
            _init_scan_cache(scan_conn)
            for fp in deleted_paths:
                scan_conn.execute("DELETE FROM scan_cache WHERE filepath = ?", (fp,))
            scan_conn.commit()
            scan_conn.close()
        logger.info("删除完成。")

    to_index = modified_paths + new_paths
    scan_cache_conn = None
    if to_index:
        cache_path = settings.scan_cache_path
        scan_cache_conn = sqlite3.connect(cache_path) if cache_path else None
        if scan_cache_conn:
            from everythingsearch.indexer import _init_scan_cache
            _init_scan_cache(scan_cache_conn)
        logger.info(
            "开始索引 %s 个文件 (%s 修改 + %s 新增)。",
            len(to_index),
            len(modified_paths),
            len(new_paths),
        )
        for i, fp in enumerate(to_index):
            mtime, stype = disk_all[fp]

            if fp in db_state:
                _delete_chunks(collection, fp)

            docs = build_documents_for_path_cached(fp, mtime, stype, scan_cache_conn)
            if docs:
                ok = False
                for attempt in range(3):
                    try:
                        vectordb.add_documents(docs)
                        ok = True
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(3)
                        else:
                            logger.error("索引失败 %s: %s", os.path.basename(fp), e)
                if not ok:
                    continue

            conn.execute(
                "INSERT OR REPLACE INTO file_index (filepath, mtime, source_type, indexed_at) VALUES (?, ?, ?, ?)",
                (fp, mtime, stype, time.time()),
            )

            if (i + 1) % 20 == 0 or i == len(to_index) - 1:
                conn.commit()
                pct = (i + 1) / len(to_index) * 100
                logger.info("增量索引进度: %.0f%% (%s/%s)", pct, i + 1, len(to_index))
                time.sleep(0.2)

        conn.commit()

    if scan_cache_conn:
        scan_cache_conn.close()
    conn.close()
    elapsed = time.time() - total_start

    logger.info("增量索引完成。")
    logger.info("新增: %s", len(new_paths))
    logger.info("修改: %s", len(modified_paths))
    logger.info("删除: %s", len(deleted_paths))
    logger.info("嵌入缓存: %s", embeddings.stats_str())
    logger.info("总耗时: %.1fs", elapsed)

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
    logger.info("状态数据库已重建: %s 文件 + %s 笔记", len(disk_files), len(disk_mweb))


def run_full():
    """Full rebuild: use indexer.build_index then rebuild state DB."""
    from everythingsearch.indexer import build_index
    build_index()
    _rebuild_state_db()


if __name__ == "__main__":
    setup_cli_logging()
    parser = argparse.ArgumentParser(description="增量/全量索引")
    parser.add_argument("--full", action="store_true", help="执行完整重建（而非增量更新）")
    args = parser.parse_args()

    if args.full:
        run_full()
    else:
        run_incremental()
