# Accuracy-First Search Technical Design

[English](SEARCH_ACCURACY_TECHNICAL_DESIGN.en.md) | [中文](SEARCH_ACCURACY_TECHNICAL_DESIGN.md)

## 1. Status

This is the publishable technical design for the accuracy-first search rebuild in EverythingSearch. It describes the planned target architecture for the next implementation phase; the current stable version does not yet provide all capabilities described here.

Confirmed implementation decisions:

1. Search may call a remote rerank API.
2. Switching the default embedding model may require a full index rebuild.
3. A separate SQLite FTS database file may be added.
4. Code-file search is not a first-class scenario for the first implementation pass, so no dedicated code-structure chunking is required initially.

## 2. Goals

The rebuild follows these priorities:

1. Accuracy first, especially Top1, Top3, and Top10 result quality.
2. Performance second, but bounded with candidate limits, timeouts, and fallbacks.
3. Old index format compatibility is not required.
4. External models may change, but the main pipeline interfaces must remain stable.

## 3. Target Query Pipeline

```text
SearchRequest
  -> QueryPlanner
  -> SparseRetriever
  -> DenseRetriever
  -> CandidateFusion
  -> Reranker
  -> FileAggregator
  -> ResultPresenter
```

Responsibilities:

- `QueryPlanner`: Classifies the query and produces sparse, dense, fusion, and rerank parameters.
- `SparseRetriever`: Uses SQLite FTS5 for literal retrieval across filename, heading, path, and content fields.
- `DenseRetriever`: Uses embeddings for semantic recall.
- `CandidateFusion`: Uses RRF to merge sparse and dense candidates.
- `Reranker`: Performs second-stage ranking over the fused TopN candidates.
- `FileAggregator`: Converts chunk-level relevance into file-level ranking.
- `ResultPresenter`: Converts ranked files into the existing API / UI result shape.

## 4. Target Indexing Pipeline

```text
FileScanner
  -> DocumentParser
  -> StructuralChunker
  -> ChunkNormalizer
  -> SparseIndexWriter
  -> DenseIndexWriter
  -> IndexManifestWriter
```

Indexing writes two indexes:

- Sparse index: `data/sparse_index.db`, used for FTS5 / BM25 retrieval.
- Dense index: vector database, with ChromaDB retained behind an adapter in the first phase.

## 5. Technology Choices

| Layer | Choice | Decision |
| --- | --- | --- |
| Sparse index | SQLite FTS5 | Default implementation |
| Dense index | ChromaDB adapter | Retained in phase one, replaceable later |
| Embedding | `text-embedding-v4` as candidate, `text-embedding-v2` as baseline | Final default decided by benchmark |
| Fusion | RRF | Default |
| Reranker | DashScope `qwen3-rerank` remote provider | Default accuracy-validation path |
| File aggregation | Custom file aggregation scorer | Default |
| Evaluation | Top1 Accuracy, MRR@10, NDCG@10, Recall@10/50, P50/P95 Latency | Default metrics |

## 6. Module Layout

Proposed new modules:

```text
everythingsearch/
├── retrieval/
│   ├── models.py
│   ├── query_planner.py
│   ├── sparse_retriever.py
│   ├── dense_retriever.py
│   ├── fusion.py
│   └── reranker.py
├── ranking/
│   └── file_aggregator.py
├── indexing/
│   ├── chunking.py
│   ├── chunk_models.py
│   ├── sparse_index_writer.py
│   └── dense_index_writer.py
└── evaluation/
    ├── metrics.py
    ├── benchmark_runner.py
    └── datasets/
```

## 7. Core Data Models

### 7.1 `IndexedChunk`

```python
@dataclass(frozen=True)
class IndexedChunk:
    chunk_id: str
    file_id: str
    filepath: str
    filename: str
    source_type: str
    filetype: str
    chunk_type: Literal["filename", "heading", "content", "table", "slide"]
    title_path: tuple[str, ...]
    content: str
    embedding_text: str
    sparse_text: str
    chunk_index: int
    mtime: float
    ctime: float
    metadata: Mapping[str, str | int | float | bool]
```

### 7.2 `QueryPlan`

```python
@dataclass(frozen=True)
class QueryPlan:
    raw_query: str
    normalized_query: str
    sparse_query: str
    dense_query: str
    query_type: Literal["exact", "semantic", "hybrid", "filename"]
    exactness_level: Literal["low", "medium", "high"]
    source_filter: str | None
    date_field: Literal["mtime", "ctime"]
    date_from: float | None
    date_to: float | None
    sparse_top_k: int
    dense_top_k: int
    fusion_top_k: int
    rerank_top_k: int
```

### 7.3 `SearchCandidate`

```python
@dataclass(frozen=True)
class SearchCandidate:
    chunk_id: str
    file_id: str
    filepath: str
    filename: str
    chunk_type: str
    content: str
    title_path: tuple[str, ...]
    source_type: str
    filetype: str
    sparse_rank: int | None
    dense_rank: int | None
    sparse_score: float | None
    dense_score: float | None
    fusion_score: float
    metadata: Mapping[str, str | int | float | bool]
```

## 8. Sparse Retrieval Design

New database:

```text
data/sparse_index.db
```

Core table:

```sql
CREATE TABLE sparse_chunks (
    chunk_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    filepath TEXT NOT NULL,
    filename TEXT NOT NULL,
    source_type TEXT NOT NULL,
    filetype TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    title_path TEXT NOT NULL,
    content TEXT NOT NULL,
    mtime REAL NOT NULL,
    ctime REAL NOT NULL,
    metadata_json TEXT NOT NULL
);
```

```sql
CREATE VIRTUAL TABLE sparse_chunks_fts USING fts5(
    filename,
    path_text,
    heading_text,
    content_text,
    chunk_id UNINDEXED,
    file_id UNINDEXED,
    tokenize = 'unicode61'
);
```

Default BM25 field weights:

```text
filename: 8.0
path_text: 3.0
heading_text: 4.0
content_text: 1.0
```

If benchmark results show that `unicode61` is insufficient for Chinese short terms, people names, or filename fragments, add a trigram auxiliary index.

## 9. Dense Retrieval Design

The first phase keeps ChromaDB, but only behind an interface:

```python
class DenseRetriever(Protocol):
    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        """Run vector recall."""
```

Embedding provider interface:

```python
class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate document vectors."""

    def embed_query(self, text: str) -> list[float]:
        """Generate a query vector."""
```

Default candidate configuration:

```python
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIMENSION = 1024
EMBEDDING_TEXT_MAX_CHARS = 1600
```

The final default model must be decided by benchmark results.

## 10. Fusion and Rerank

Fusion uses RRF by default:

```text
rrf_score = sum(weight(source) / (k + rank(source)))
```

Default parameters:

```text
k = 60
sparse_weight = 1.0
dense_weight = 1.0
```

Reranker interface:

```python
class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[SearchCandidate],
        top_n: int,
    ) -> list[RerankedCandidate]:
        """Run second-stage ranking over fused candidates."""
```

Default configuration:

```python
RERANK_ENABLED = True
RERANK_PROVIDER = "dashscope"
RERANK_MODEL = "qwen3-rerank"
RERANK_TOP_K = 50
RERANK_TIMEOUT_SEC = 8
RERANK_MAX_CANDIDATES = 60
```

Fallback rules:

- Reranker timeout: use fusion order.
- Reranker rate limit: use fusion order and log the fallback.
- Invalid reranker response: use fusion order.
- Fallbacks must not return empty results.

## 11. File-Level Aggregation

File-level ranking replaces the current “keep only the best chunk per file” strategy.

```python
class FileAggregator(Protocol):
    def aggregate(
        self,
        candidates: list[RerankedCandidate],
        plan: QueryPlan,
    ) -> list[FileRankResult]:
        """Aggregate chunk-level results into file-level results."""
```

Default scoring:

```text
file_score =
  best_rerank_score * 0.70
  + second_rerank_score * 0.15
  + third_rerank_score * 0.05
  + filename_bonus
  + heading_bonus
  + exact_phrase_bonus
  + multi_hit_bonus
  - large_file_penalty
```

All weights should be exposed as configuration first, then tuned by benchmark results.

## 12. Chunking Strategy

The first pass optimizes around document structure but does not add code AST parsing:

- Markdown: split by heading hierarchy.
- PDF: split by page and paragraph; short title-like lines enter the title path.
- Word: detect headings through paragraph styles; tables become dedicated table chunks.
- PPT: one slide chunk per slide; slide title enters the title path.
- Excel: create table chunks by sheet, header, and row windows.
- Code: treat as plain text; not a first-class scenario.

Initial recommended sizes:

```text
content_chunk_target_chars = 900
content_chunk_max_chars = 1400
content_chunk_overlap_chars = 120
rerank_text_max_chars = 1200
embedding_text_max_chars = 1600
```

## 13. Benchmark

New evaluation dataset:

```text
everythingsearch/evaluation/datasets/search_eval.jsonl
```

Line format:

```json
{
  "query": "quarterly budget excel",
  "query_type": "hybrid",
  "relevant_files": [
    {"filepath": "/abs/path/budget.xlsx", "grade": 3}
  ],
  "must_include": [],
  "notes": "budget-topic query"
}
```

Required metrics:

- `Top1Accuracy`
- `Recall@10`
- `Recall@50`
- `MRR@10`
- `NDCG@10`
- `P50LatencyMs`
- `P95LatencyMs`
- `RerankFallbackRate`

Experiment groups:

```text
baseline_current
sparse_fts_only
dense_only_v2
dense_only_v4
sparse_dense_rrf
sparse_dense_rrf_rerank
sparse_dense_rrf_rerank_file_agg
```

## 14. Implementation Order

1. Add evaluation benchmark without changing online search.
2. Add FTS5 sparse index and sparse retriever.
3. Add QueryPlan and retrieval models.
4. Add dense retriever adapter.
5. Add RRF fusion.
6. Add DashScope reranker provider.
7. Add file aggregator.
8. Rebuild structural chunking.
9. Tune weights and default models with benchmark results.
10. Switch the new pipeline into the default search path.

## 15. References

- SQLite FTS5 official documentation: <https://www.sqlite.org/fts5.html>
- Chroma metadata / where filter official documentation: <https://docs.trychroma.com/docs/querying-collections/metadata-filtering>
- Alibaba Cloud Model Studio embedding official documentation: <https://www.alibabacloud.com/help/en/model-studio/user-guide/embedding>
- Alibaba Cloud Model Studio text rerank official documentation: <https://www.alibabacloud.com/help/en/model-studio/text-rerank-api>
