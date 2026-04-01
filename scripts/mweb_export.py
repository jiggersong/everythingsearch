#!/usr/bin/env python3
"""
MWeb Library → Markdown 导出工具

功能:
  - 按 MWeb 分类目录结构导出为 Markdown 文件
  - 在 YAML front matter 中保留标签、分类、日期等元数据
  - 复制关联的媒体文件 (图片/附件) 并修正引用路径
  - 生成 _index.json 索引文件, 方便 EverythingSearch 检索
  - 增量导出: 仅更新有变动的笔记

配置:
  所有参数通过同目录下的 config.toml 管理
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ─── 内部化配置加载 ────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from everythingsearch.infra.settings import get_settings

def load_config() -> dict:
    settings = get_settings()
    
    if not settings.enable_mweb:
        sys.exit("❌ ENABLE_MWEB 未开启，放弃运行 MWeb 扫描导出")

    if not settings.mweb_dir:
        sys.exit("❌ 缺失 MWeb 导出目标目录配置")

    return {
        "library": os.path.expanduser(settings.mweb_library_path),
        "output":  os.path.expanduser(settings.mweb_dir),
        "dry_run": False,
        "force":   False,
    }


# ─── 数据库读取 ─────────────────────────────────────────────────────────────

def open_db(lib_path: str) -> sqlite3.Connection:
    db_path = os.path.join(lib_path, "mainlib.db")
    if not os.path.exists(db_path):
        sys.exit(f"❌ 找不到数据库: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_categories(conn: sqlite3.Connection) -> dict:
    """返回 {uuid: {name, pid, children: []}} 的分类树"""
    rows = conn.execute("SELECT uuid, pid, name FROM cat").fetchall()
    cats = {}
    for r in rows:
        cats[r["uuid"]] = {"name": r["name"], "pid": r["pid"], "children": []}
    for uuid, info in cats.items():
        parent = info["pid"]
        if parent and parent in cats:
            cats[parent]["children"].append(uuid)
    return cats


def build_cat_path(cats: dict, uuid: int) -> str:
    """沿 pid 链向上回溯, 构建 '顶级/二级/三级' 路径"""
    parts = []
    visited = set()
    cur = uuid
    while cur and cur in cats:
        if cur in visited:
            break
        visited.add(cur)
        parts.append(cats[cur]["name"])
        cur = cats[cur]["pid"]
    parts.reverse()
    return "/".join(parts)


def load_articles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, uuid, dateAdd, dateModif, docName FROM article"
    ).fetchall()
    return [dict(r) for r in rows]


def load_cat_article_map(conn: sqlite3.Connection) -> dict:
    """返回 {article_uuid: [cat_uuid, ...]}"""
    rows = conn.execute("SELECT rid, aid FROM cat_article").fetchall()
    mapping = {}
    for r in rows:
        mapping.setdefault(r["aid"], []).append(r["rid"])
    return mapping


def load_tag_article_map(conn: sqlite3.Connection, tags: dict) -> dict:
    """返回 {article_uuid: [tag_name, ...]}"""
    rows = conn.execute("SELECT rid, aid FROM tag_article").fetchall()
    mapping = {}
    for r in rows:
        tag_name = tags.get(r["rid"])
        if tag_name:
            mapping.setdefault(r["aid"], []).append(tag_name)
    return mapping


def load_tags(conn: sqlite3.Connection) -> dict:
    """返回 {uuid: name}"""
    rows = conn.execute("SELECT uuid, name FROM tag").fetchall()
    return {r["uuid"]: r["name"] for r in rows}


# ─── Markdown 处理 ──────────────────────────────────────────────────────────

def extract_title(content: str) -> str:
    """从 Markdown 内容的第一个标题行提取标题"""
    for line in content.splitlines():
        m = re.match(r'^#{1,6}\s+(.+)', line)
        if m:
            return m.group(1).strip()
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    return first_line[:80] if first_line else "Untitled"


def sanitize_filename(name: str) -> str:
    """将字符串转为安全的文件/目录名"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:120] if name else "Untitled"


def ts_to_iso(ts: int | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        return ""


def build_front_matter(title: str, tags: list[str], categories: list[str],
                       date_add: str, date_mod: str, mweb_uuid: int) -> str:
    """生成 YAML front matter"""
    lines = ["---"]
    lines.append(f"title: \"{title}\"")
    if date_add:
        lines.append(f"date: \"{date_add}\"")
    if date_mod:
        lines.append(f"updated: \"{date_mod}\"")
    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - \"{t}\"")
    if categories:
        lines.append("categories:")
        for c in categories:
            lines.append(f"  - \"{c}\"")
    lines.append(f"mweb_uuid: {mweb_uuid}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def fix_media_paths(content: str, note_uuid: int, rel_media_dir: str) -> str:
    """将 media/{note_uuid}/xxx 替换为导出后的相对路径"""
    pattern = re.compile(r'(!\[.*?\]\()media/' + str(note_uuid) + r'/([^)]+)\)')
    replacement = rf'\1{rel_media_dir}/\2)'
    return pattern.sub(replacement, content)


# ─── 增量状态管理 ────────────────────────────────────────────────────────────

STATE_FILENAME = "_export_state.json"


def load_export_state(output_dir: str) -> dict:
    state_path = os.path.join(output_dir, STATE_FILENAME)
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_export_state(output_dir: str, state: dict):
    state_path = os.path.join(output_dir, STATE_FILENAME)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _media_hash(media_dir: str) -> str:
    """基于文件名 + 大小 + mtime 快速计算媒体目录指纹"""
    if not os.path.isdir(media_dir):
        return ""
    entries = []
    for f in sorted(Path(media_dir).rglob("*")):
        if f.is_file():
            st = f.stat()
            entries.append(f"{f.relative_to(media_dir)}:{st.st_size}:{st.st_mtime}")
    return hashlib.sha256("|".join(entries).encode()).hexdigest()


# ─── 导出主逻辑 ─────────────────────────────────────────────────────────────

def export_notes(lib_path: str, output_dir: str, dry_run: bool = False,
                 force: bool = False):
    conn = open_db(lib_path)

    print(f"📖 MWeb 库: {lib_path}")
    print(f"📁 输出目录: {output_dir}")
    if force:
        print("🔄 强制全量导出")

    cats = load_categories(conn)
    tags = load_tags(conn)
    articles = load_articles(conn)
    cat_map = load_cat_article_map(conn)
    tag_map = load_tag_article_map(conn, tags)

    docs_dir = os.path.join(lib_path, "docs")
    media_src = os.path.join(docs_dir, "media")

    prev_state = {} if force else load_export_state(output_dir)
    new_state: dict[str, dict] = {}

    stats = {
        "exported": 0, "skipped": 0, "unchanged": 0,
        "media_copied": 0, "errors": 0, "cleaned": 0,
    }
    index_entries = []
    seen_paths = {}

    for art in articles:
        a_uuid = art["uuid"]
        md_file = os.path.join(docs_dir, f"{a_uuid}.md")

        if not os.path.exists(md_file):
            stats["skipped"] += 1
            continue

        try:
            with open(md_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            print(f"  ⚠️ 读取失败 {a_uuid}: {e}")
            stats["errors"] += 1
            continue

        title = extract_title(content)
        art_tags = tag_map.get(a_uuid, [])
        art_cats_uuids = cat_map.get(a_uuid, [])
        art_cat_paths = [build_cat_path(cats, cu) for cu in art_cats_uuids]

        if art_cat_paths:
            primary_path = art_cat_paths[0]
        else:
            primary_path = "未分类"

        safe_title = sanitize_filename(title)
        dest_folder = os.path.join(output_dir, *[sanitize_filename(p) for p in primary_path.split("/")])
        dest_file = os.path.join(dest_folder, f"{safe_title}.md")

        if dest_file in seen_paths:
            seen_paths[dest_file] += 1
            base, ext = os.path.splitext(dest_file)
            dest_file = f"{base}_{seen_paths[dest_file]}{ext}"
        else:
            seen_paths[dest_file] = 0

        date_add = ts_to_iso(art["dateAdd"])
        date_mod = ts_to_iso(art["dateModif"])

        note_media_src = os.path.join(media_src, str(a_uuid))
        has_media = os.path.isdir(note_media_src)

        if has_media:
            media_dest_name = "media"
            rel_media_dir = media_dest_name
            content = fix_media_paths(content, a_uuid, rel_media_dir)

        front_matter = build_front_matter(
            title, art_tags, art_cat_paths, date_add, date_mod, a_uuid
        )
        final_content = front_matter + content

        # ── 增量检测: 内容 + 媒体是否有变化 ──
        c_hash = _content_hash(final_content)
        m_hash = _media_hash(note_media_src) if has_media else ""

        prev_art = prev_state.get(str(a_uuid), {})
        content_changed = (c_hash != prev_art.get("content_hash"))
        media_changed = (m_hash != prev_art.get("media_hash", ""))
        dest_exists = os.path.exists(dest_file)

        # 如果目标路径变了 (如标题/分类变更), 清理旧文件
        old_dest_rel = prev_art.get("dest_file")
        if old_dest_rel:
            old_dest_abs = os.path.join(output_dir, old_dest_rel)
            if os.path.abspath(old_dest_abs) != os.path.abspath(dest_file):
                if not dry_run and os.path.exists(old_dest_abs):
                    os.remove(old_dest_abs)
            old_media_rel = prev_art.get("media_dest")
            if old_media_rel:
                old_media_abs = os.path.join(output_dir, old_media_rel)
                media_dest_abs = os.path.join(dest_folder, safe_title + "_media") if has_media else ""
                if media_dest_abs and os.path.abspath(old_media_abs) != os.path.abspath(media_dest_abs):
                    if not dry_run and os.path.isdir(old_media_abs):
                        shutil.rmtree(old_media_abs)

        needs_update = content_changed or media_changed or not dest_exists

        art_state: dict[str, str] = {
            "content_hash": c_hash,
            "media_hash": m_hash,
            "dest_file": os.path.relpath(dest_file, output_dir),
        }

        if not needs_update:
            # 内容未变更, 跳过写入
            if has_media:
                art_state["media_dest"] = os.path.relpath(
                    os.path.join(dest_folder, safe_title + "_media"), output_dir)
            new_state[str(a_uuid)] = art_state
            stats["unchanged"] += 1
        elif dry_run:
            print(f"  [DRY] {dest_file}")
            stats["exported"] += 1
        else:
            os.makedirs(dest_folder, exist_ok=True)
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(final_content)

            if has_media:
                media_dest = os.path.join(dest_folder, safe_title + "_media")
                if os.path.exists(note_media_src):
                    shutil.copytree(note_media_src, media_dest, dirs_exist_ok=True)
                    media_count = sum(1 for _ in Path(media_dest).rglob("*") if _.is_file())
                    stats["media_copied"] += media_count

                    content_fixed = fix_media_paths(
                        content, a_uuid, safe_title + "_media"
                    )
                    final_content = front_matter + content_fixed
                    with open(dest_file, "w", encoding="utf-8") as f:
                        f.write(final_content)
                    c_hash = _content_hash(final_content)
                    art_state["content_hash"] = c_hash

                art_state["media_dest"] = os.path.relpath(media_dest, output_dir)

            new_state[str(a_uuid)] = art_state
            stats["exported"] += 1

        index_entries.append({
            "title": title,
            "file": os.path.relpath(dest_file, output_dir),
            "tags": art_tags,
            "categories": art_cat_paths,
            "date": date_add,
            "updated": date_mod,
            "mweb_uuid": a_uuid,
        })

        total = stats["exported"] + stats["unchanged"]
        print(f"  处理 {total}/{len(articles)}...", end="\r")

    # ── 清理已从 MWeb 中删除的笔记 ──
    if not dry_run:
        for old_uuid, old_info in prev_state.items():
            if old_uuid not in new_state:
                old_f = os.path.join(output_dir, old_info.get("dest_file", ""))
                if os.path.exists(old_f):
                    os.remove(old_f)
                    stats["cleaned"] += 1
                old_m = old_info.get("media_dest")
                if old_m:
                    old_mp = os.path.join(output_dir, old_m)
                    if os.path.isdir(old_mp):
                        shutil.rmtree(old_mp)

    if not dry_run:
        index_path = os.path.join(output_dir, "_index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_entries, f, ensure_ascii=False, indent=2)
        save_export_state(output_dir, new_state)

    conn.close()

    print()
    print("=" * 50)
    print("✅ 导出完成!")
    print(f"  笔记更新: {stats['exported']}")
    print(f"  未变更 (跳过): {stats['unchanged']}")
    print(f"  跳过 (无文件): {stats['skipped']}")
    print(f"  媒体文件: {stats['media_copied']}")
    print(f"  清理旧文件: {stats['cleaned']}")
    print(f"  错误: {stats['errors']}")
    if not dry_run:
        print(f"  索引文件: {os.path.join(output_dir, '_index.json')}")
    print("=" * 50)

    return stats


def main():
    cfg = load_config()

    if not os.path.isdir(cfg["library"]):
        sys.exit(f"❌ MWeb Library 不存在: {cfg['library']}")

    export_notes(cfg["library"], cfg["output"], cfg["dry_run"], cfg["force"])


if __name__ == "__main__":
    main()
