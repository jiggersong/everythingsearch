"""Tests for NL search query refinement (instructional filler stripping)."""

from everythingsearch.services.nl_search_service import (
    _refine_slots_q,
    _strip_search_filler_phrases,
)


def test_strip_chinese_instructional_phrase():
    assert _strip_search_filler_phrases("帮我搜索下黄晓容的信息") == "黄晓容"


def test_strip_preserves_plain_name():
    assert _strip_search_filler_phrases("黄晓容") == "黄晓容"


def test_refine_when_model_echoes_full_sentence():
    u = "帮我搜索下黄晓容的信息"
    assert _refine_slots_q(u, u) == "黄晓容"
    assert _refine_slots_q(u, "帮我搜索下黄晓容的信息") == "黄晓容"


def test_refine_when_model_already_short():
    u = "帮我搜索下黄晓容的信息"
    assert _refine_slots_q(u, "黄晓容") == "黄晓容"


def test_refine_no_instructional_no_change():
    assert _refine_slots_q("黄晓容", "黄晓容") == "黄晓容"
