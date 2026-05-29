"""全量重建计划与环境测试。"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

from everythingsearch.indexing.full_rebuild_plan import FullRebuildPlan, add_full_rebuild_arguments
from everythingsearch.indexing.full_rebuild_environment import _paths_for_plan


def test_resume_forces_keep_caches():
    parser = argparse.ArgumentParser()
    add_full_rebuild_arguments(parser)
    args = parser.parse_args(["--resume"])
    plan = FullRebuildPlan.from_namespace(args)
    assert plan.resume is True
    assert plan.keep_embedding_cache is True
    assert plan.keep_scan_cache is True


def test_keep_caches_sets_both():
    parser = argparse.ArgumentParser()
    add_full_rebuild_arguments(parser)
    args = parser.parse_args(["--keep-caches"])
    plan = FullRebuildPlan.from_namespace(args)
    assert plan.keep_embedding_cache is True
    assert plan.keep_scan_cache is True


def test_default_plan_wipes_caches(tmp_path):
    settings = SimpleNamespace(
        sparse_index_path=str(tmp_path / "sparse.db"),
        index_state_db=str(tmp_path / "state.db"),
        rebuild_staging_path=str(tmp_path / "staging.db"),
        rebuild_checkpoint_path=str(tmp_path / "checkpoint.db"),
        persist_directory=str(tmp_path / "chroma"),
        embedding_cache_path=str(tmp_path / "embedding.db"),
        scan_cache_path=str(tmp_path / "scan_cache.db"),
    )
    plan = FullRebuildPlan()
    to_remove, to_keep = _paths_for_plan(settings, plan)
    assert settings.embedding_cache_path in {str(p) for p in to_remove}
    assert settings.scan_cache_path in {str(p) for p in to_remove}
    assert to_keep == []
