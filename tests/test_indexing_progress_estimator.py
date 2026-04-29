"""索引进度成本估算测试。"""

from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.progress_estimator import (
    DEFAULT_EMBEDDING_MAX_CHARS,
    estimate_cost_from_chunks,
    estimate_full_cost_from_file_count,
    estimate_incremental_cost,
    estimate_tokens_from_text,
    estimate_tokens_from_texts,
    load_historical_chunks_per_file,
    normalize_embedding_text_for_estimate,
)


class TestProgressEstimator:
    """测试索引规模与 Token 估算。"""

    def test_empty_text_uses_minimum_token(self):
        """空文本应按 embedding 实际口径归一为空格并返回最小 Token。"""
        assert normalize_embedding_text_for_estimate("") == " "
        assert estimate_tokens_from_text("") == 1

    def test_token_estimate_truncates_to_embedding_limit(self):
        """Token 估算必须按 CachedEmbeddings 的 600 字符截断口径计算。"""
        long_text = "x" * (DEFAULT_EMBEDDING_MAX_CHARS * 2)

        assert len(normalize_embedding_text_for_estimate(long_text)) == DEFAULT_EMBEDDING_MAX_CHARS
        assert estimate_tokens_from_text(long_text, chars_per_token=1.0) == DEFAULT_EMBEDDING_MAX_CHARS

    def test_estimate_tokens_from_texts_sums_each_text(self):
        """批量估算应累加每条文本的估算值。"""
        assert estimate_tokens_from_texts(["abc", "defg"]) == 5

    def test_zero_file_estimate_returns_zero_cost(self):
        """零文件场景应返回稳定 0 值，而不是 None。"""
        estimate = estimate_incremental_cost(0)

        assert estimate.estimated_chunk_count == 0
        assert estimate.estimated_input_token_count == 0
        assert estimate.estimated_remote_embedding_text_count == 0
        assert estimate.estimated_total_seconds == 0.0

    def test_file_count_estimate_uses_history_when_available(self):
        """存在历史均值时应按历史 chunks_per_file 估算。"""
        estimate = estimate_full_cost_from_file_count(
            10,
            historical_chunks_per_file=2.5,
            historical_seconds_per_file=0.2,
        )

        assert estimate.estimated_chunk_count == 25
        assert estimate.estimated_total_seconds == 2.0

    def test_chunk_estimate_uses_actual_embedding_text(self):
        """chunk 级估算应基于 IndexedChunk.embedding_text。"""
        chunks = [
            _build_chunk("a", "hello"),
            _build_chunk("b", "x" * 1200),
        ]

        estimate = estimate_cost_from_chunks(chunks)

        assert estimate.estimated_chunk_count == 2
        assert estimate.estimated_remote_embedding_text_count == 2
        assert estimate.estimated_input_token_count == (
            estimate_tokens_from_text("hello")
            + estimate_tokens_from_text("x" * 1200)
        )

    def test_load_historical_chunks_does_not_create_missing_db(self, tmp_path):
        """读取历史均值时不应为了只读估算创建新 sparse DB。"""
        missing_db = tmp_path / "missing.db"

        result = load_historical_chunks_per_file(str(missing_db), fallback_file_count=10)

        assert result is None
        assert not missing_db.exists()


def _build_chunk(chunk_id: str, embedding_text: str) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=chunk_id,
        file_id="file-a",
        filepath="/tmp/a.md",
        filename="a.md",
        source_type="file",
        filetype=".md",
        chunk_type="content",
        title_path=(),
        content=embedding_text,
        embedding_text=embedding_text,
        sparse_text=embedding_text,
        chunk_index=0,
        mtime=1.0,
        ctime=1.0,
        metadata={},
    )
