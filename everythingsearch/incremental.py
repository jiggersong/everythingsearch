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

# Repo-root `config.py` is imported by name; direct `python everythingsearch/incremental.py`
# only puts this package dir on sys.path, so add project root first.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from everythingsearch.indexer import (
    normalize_path,
    build_documents_for_path_cached,
)
from everythingsearch.embedding_cache import CachedEmbeddings
from langchain_chroma import Chroma
import chromadb


DB_PATH = config.INDEX_STATE_DB


def _ensure_dashscope_api_key() -> bool:
    if os.environ.get("DASHSCOPE_API_KEY"):
        return True
    if getattr(config, "MY_API_KEY", ""):
        os.environ["DASHSCOPE_API_KEY"] = config.MY_API_KEY
        return True
    print("❌ 未配置 DashScope API Key。请设置环境变量 DASHSCOPE_API_KEY 或在 config.py 中填写 MY_API_KEY。")
    return False


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
    result = {}
    for target_dir in config.get_target_dirs():
        if not os.path.isdir(target_dir):
            continue
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.startswith('.'):
                    continue
                _, ext = os.path.splitext(f)
                ext = ext.lower()
                if ext not in config.SUPPORTED_EXTENSIONS:
                    continue
                raw_path = os.path.join(root, f)
                filepath = normalize_path(raw_path)
                if config.INDEX_ONLY_KEYWORDS:
                    if not any(kw in filepath for kw in config.INDEX_ONLY_KEYWORDS):
                        continue
                try:
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue
                result[filepath] = (mtime, "file")
    return result


def _scan_disk_mweb() -> dict[str, tuple[float, str]]:
    """Scan MWEB_DIR and return {filepath: (mtime, 'mweb')}."""
    result = {}
    if not getattr(config, "ENABLE_MWEB", True):
        return result
    mweb_dir = config.MWEB_DIR
    if not os.path.isdir(mweb_dir):
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
    total_start = time.time()

    print("=" * 50)
    print("📦 增量索引开始")
    print("=" * 50)

    if getattr(config, "ENABLE_MWEB", True) and os.path.isfile(config.MWEB_EXPORT_SCRIPT):
        print("\n📓 运行 MWeb 导出脚本...")
        try:
            subprocess.run(
                [sys.executable, config.MWEB_EXPORT_SCRIPT],
                check=True,
                timeout=120,
            )
            print("  ✅ MWeb 导出完成")
        except Exception as e:
            print(f"  ⚠️ MWeb 导出失败 (继续使用已有文件): {e}")

    conn = sqlite3.connect(DB_PATH)
    _init_state_db(conn)

    print("\n🔍 扫描文件系统...")
    disk_files = _scan_disk_files()
    print(f"  文件: {len(disk_files)}")

    disk_mweb = _scan_disk_mweb()
    print(f"  MWeb 笔记: {len(disk_mweb)}")

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

    print(f"\n📊 变更统计:")
    print(f"  新增: {len(new_paths)}")
    print(f"  修改: {len(modified_paths)}")
    print(f"  删除: {len(deleted_paths)}")

    if not new_paths and not modified_paths and not deleted_paths:
        print("\n✅ 索引已是最新，无需更新。")
        conn.close()
        return

    client = chromadb.PersistentClient(path=config.PERSIST_DIRECTORY)
    existing_collections = [c.name for c in client.list_collections()]

    if "local_files" not in existing_collections:
        print("\n⚠️ ChromaDB collection 不存在，将执行完整索引...")
        conn.close()
        from everythingsearch.indexer import build_index
        build_index()
        _rebuild_state_db()
        return

    collection = client.get_collection("local_files")

    if not _ensure_dashscope_api_key():
        conn.close()
        return
    embeddings = CachedEmbeddings(
        model=config.EMBEDDING_MODEL,
        cache_path=config.EMBEDDING_CACHE_PATH,
    )
    vectordb = Chroma(
        client=client,
        embedding_function=embeddings,
        collection_name="local_files",
    )

    if deleted_paths:
        print(f"\n🗑️ 删除 {len(deleted_paths)} 个已移除文件的索引...")
        for fp in deleted_paths:
            _delete_chunks(collection, fp)
            conn.execute("DELETE FROM file_index WHERE filepath = ?", (fp,))
        conn.commit()
        # 同步清理扫描缓存，避免缓存膨胀
        cache_path = getattr(config, "SCAN_CACHE_PATH", None)
        if cache_path:
            from everythingsearch.indexer import _init_scan_cache
            scan_conn = sqlite3.connect(cache_path)
            _init_scan_cache(scan_conn)
            for fp in deleted_paths:
                scan_conn.execute("DELETE FROM scan_cache WHERE filepath = ?", (fp,))
            scan_conn.commit()
            scan_conn.close()
        print("  ✅ 删除完成")

    to_index = modified_paths + new_paths
    scan_cache_conn = None
    if to_index:
        cache_path = getattr(config, "SCAN_CACHE_PATH", None)
        scan_cache_conn = sqlite3.connect(cache_path) if cache_path else None
        if scan_cache_conn:
            from everythingsearch.indexer import _init_scan_cache
            _init_scan_cache(scan_cache_conn)
        print(f"\n🧠 索引 {len(to_index)} 个文件 ({len(modified_paths)} 修改 + {len(new_paths)} 新增)...")
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
                            print(f"  ❌ 索引失败 {os.path.basename(fp)}: {e}")
                if not ok:
                    continue

            conn.execute(
                "INSERT OR REPLACE INTO file_index (filepath, mtime, source_type, indexed_at) VALUES (?, ?, ?, ?)",
                (fp, mtime, stype, time.time()),
            )

            if (i + 1) % 20 == 0 or i == len(to_index) - 1:
                conn.commit()
                pct = (i + 1) / len(to_index) * 100
                print(f"  进度: {pct:.0f}% ({i + 1}/{len(to_index)})")
                time.sleep(0.2)

        conn.commit()

    if scan_cache_conn:
        scan_cache_conn.close()
    conn.close()
    elapsed = time.time() - total_start

    print("\n" + "=" * 50)
    print("🎉 增量索引完成！")
    print(f"  新增: {len(new_paths)}")
    print(f"  修改: {len(modified_paths)}")
    print(f"  删除: {len(deleted_paths)}")
    print(f"  嵌入缓存: {embeddings.stats_str()}")
    print(f"  总耗时: {elapsed:.1f}s")
    print("=" * 50)



def _rebuild_state_db():
    """Rebuild the state DB after a full index by scanning disk state."""
    conn = sqlite3.connect(DB_PATH)
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
    print(f"📋 状态数据库已重建: {len(disk_files)} 文件 + {len(disk_mweb)} 笔记")


def run_full():
    """Full rebuild: use indexer.build_index then rebuild state DB."""
    from everythingsearch.indexer import build_index
    build_index()
    _rebuild_state_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="增量/全量索引")
    parser.add_argument("--full", action="store_true", help="执行完整重建（而非增量更新）")
    args = parser.parse_args()

    if args.full:
        run_full()
    else:
        run_incremental()
