"""全量重建 CLI 计划（与 orchestrator 解耦）。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class FullRebuildPlan:
    """全量重建运行时计划。"""

    keep_embedding_cache: bool = False
    keep_scan_cache: bool = False
    resume: bool = False
    dry_run: bool = False
    skip_sparse_optimize: bool = False

    @classmethod
    def from_namespace(cls, args: argparse.Namespace) -> FullRebuildPlan:
        """从 argparse 解析结果构造计划。"""
        keep_embedding = bool(args.keep_embedding_cache or args.keep_caches)
        keep_scan = bool(args.keep_scan_cache or args.keep_caches)
        if args.resume:
            keep_embedding = True
            keep_scan = True
        return cls(
            keep_embedding_cache=keep_embedding,
            keep_scan_cache=keep_scan,
            resume=bool(args.resume),
            dry_run=bool(args.dry_run),
            skip_sparse_optimize=bool(args.skip_sparse_optimize),
        )

    @classmethod
    def keep_caches_for_fallback(cls) -> FullRebuildPlan:
        """增量回退全量：保留两类缓存，不续跑。"""
        return cls(keep_embedding_cache=True, keep_scan_cache=True)


def add_full_rebuild_arguments(parser: argparse.ArgumentParser) -> None:
    """向 ArgumentParser 注册全量重建相关参数。"""
    parser.add_argument(
        "--keep-embedding-cache",
        action="store_true",
        help="保留 embedding 向量缓存（省 Token）",
    )
    parser.add_argument(
        "--keep-scan-cache",
        action="store_true",
        help="保留文件解析缓存（省重解析时间）",
    )
    parser.add_argument(
        "--keep-caches",
        action="store_true",
        help="同时保留 embedding 与 scan 缓存",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从 rebuild_checkpoint 断点续跑（强制保留两类缓存）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将删除/保留的数据文件，不执行重建",
    )
    parser.add_argument(
        "--skip-sparse-optimize",
        action="store_true",
        help="Sparse 写入完成后跳过 FTS5 optimize",
    )
