# 检索准确率优先改造技术设计

[English](SEARCH_ACCURACY_TECHNICAL_DESIGN.en.md) | [中文](SEARCH_ACCURACY_TECHNICAL_DESIGN.md)

## 1. 状态

本文档是 EverythingSearch 检索准确率优先改造的发布版技术设计。它描述的是下一阶段计划实施的目标架构，不代表当前稳定版本已经具备这些能力。

已确认的实施决策：

1. 允许搜索时调用远端 rerank API。
2. 接受切换 embedding 默认模型后全量重建索引。
3. 接受新增独立 SQLite FTS 数据库文件。
4. 代码文件检索不作为一等场景，首轮不做代码结构专用切块。

## 2. 设计目标

本次改造按以下优先级执行：

1. 准确率优先，重点提升 Top1、Top3、Top10 结果质量。
2. 性能次级，但必须通过候选规模、超时和降级策略保持可控。
3. 不兼容旧索引格式也可以接受。
4. 外部模型可替换，主链路接口必须稳定。

## 3. 目标查询链路

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

职责划分：

- `QueryPlanner`：判断查询类型，生成稀疏、稠密、融合、rerank 的执行参数。
- `SparseRetriever`：基于 SQLite FTS5 处理文件名、标题、路径、正文的字面检索。
- `DenseRetriever`：基于 embedding 向量处理语义召回。
- `CandidateFusion`：用 RRF 融合稀疏与稠密候选。
- `Reranker`：对融合后的 TopN 候选做二阶段精排。
- `FileAggregator`：把 chunk 级结果聚合成文件级排序。
- `ResultPresenter`：输出当前 API / UI 可消费的结果格式。

## 4. 目标索引链路

```text
FileScanner
  -> DocumentParser
  -> StructuralChunker
  -> ChunkNormalizer
  -> SparseIndexWriter
  -> DenseIndexWriter
  -> IndexManifestWriter
```

索引侧同时写入两套索引：

- 稀疏索引：`data/sparse_index.db`，用于 FTS5 / BM25 检索。
- 稠密索引：向量库，第一阶段通过适配层继续使用 ChromaDB。

## 5. 技术选型

| 层级 | 选型 | 结论 |
| --- | --- | --- |
| 稀疏索引 | SQLite FTS5 | 默认落地方案 |
| 稠密索引 | ChromaDB 适配层 | 第一阶段保留，后续可替换 |
| embedding | `text-embedding-v4` 作为候选，`text-embedding-v2` 作为 baseline | 通过 benchmark 决定最终默认 |
| 融合 | RRF | 默认方案 |
| reranker | DashScope `qwen3-rerank` 远端 Provider | 默认准确率验证路径 |
| 文件聚合 | 自研 file aggregation scorer | 默认方案 |
| 评测 | Top1 Accuracy、MRR@10、NDCG@10、Recall@10/50、P50/P95 Latency | 默认指标 |

## 6. 模块结构

建议新增模块：

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

## 7. 核心数据模型

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

## 8. 稀疏检索设计

新增数据库：

```text
data/sparse_index.db
```

核心表：

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

默认 BM25 字段权重：

```text
filename: 8.0
path_text: 3.0
heading_text: 4.0
content_text: 1.0
```

如果 benchmark 证明 `unicode61` 对中文短词、人名或文件名片段效果不足，再新增 trigram 辅助索引。

## 9. 稠密检索设计

第一阶段继续使用 ChromaDB，但只通过接口访问：

```python
class DenseRetriever(Protocol):
    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        """执行向量召回。"""
```

embedding Provider 接口：

```python
class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """生成文档向量。"""

    def embed_query(self, text: str) -> list[float]:
        """生成查询向量。"""
```

默认候选配置：

```python
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIMENSION = 1024
EMBEDDING_TEXT_MAX_CHARS = 1600
```

最终默认模型必须由 benchmark 决定。

## 10. 融合与 rerank

融合默认使用 RRF：

```text
rrf_score = sum(weight(source) / (k + rank(source)))
```

默认参数：

```text
k = 60
sparse_weight = 1.0
dense_weight = 1.0
```

reranker 接口：

```python
class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[SearchCandidate],
        top_n: int,
    ) -> list[RerankedCandidate]:
        """对融合候选进行二阶段精排。"""
```

默认配置：

```python
RERANK_ENABLED = True
RERANK_PROVIDER = "dashscope"
RERANK_MODEL = "qwen3-rerank"
RERANK_TOP_K = 50
RERANK_TIMEOUT_SEC = 8
RERANK_MAX_CANDIDATES = 60
```

降级规则：

- reranker 超时：使用 fusion 排序。
- reranker 限流：使用 fusion 排序并记录日志。
- reranker 返回异常：使用 fusion 排序。
- 降级不得返回空结果。

## 11. 文件聚合排序

文件级排序替换当前“每文件只保留最佳 chunk”的策略。

```python
class FileAggregator(Protocol):
    def aggregate(
        self,
        candidates: list[RerankedCandidate],
        plan: QueryPlan,
    ) -> list[FileRankResult]:
        """将 chunk 级结果聚合为文件级结果。"""
```

默认评分：

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

所有权重先暴露为配置，最终由 benchmark 调整。

## 12. 切块策略

首轮按文档结构优化，但不做代码 AST：

- Markdown：按标题层级切分。
- PDF：按页和段落切分，短标题行进入标题路径。
- Word：按段落样式识别标题，表格单独生成 table chunk。
- PPT：每页一个 slide chunk，页标题进入标题路径。
- Excel：按 sheet、表头和行窗口生成 table chunk。
- 代码：按普通文本处理，不作为一等场景。

推荐初始大小：

```text
content_chunk_target_chars = 900
content_chunk_max_chars = 1400
content_chunk_overlap_chars = 120
rerank_text_max_chars = 1200
embedding_text_max_chars = 1600
```

## 13. Benchmark

新增评测集：

```text
everythingsearch/evaluation/datasets/search_eval.jsonl
```

单行格式：

```json
{
  "query": "季度预算 excel",
  "query_type": "hybrid",
  "relevant_files": [
    {"filepath": "/abs/path/budget.xlsx", "grade": 3}
  ],
  "must_include": [],
  "notes": "预算主题查询"
}
```

必须输出指标：

- `Top1Accuracy`
- `Recall@10`
- `Recall@50`
- `MRR@10`
- `NDCG@10`
- `P50LatencyMs`
- `P95LatencyMs`
- `RerankFallbackRate`

实验组：

```text
baseline_current
sparse_fts_only
dense_only_v2
dense_only_v4
sparse_dense_rrf
sparse_dense_rrf_rerank
sparse_dense_rrf_rerank_file_agg
```

## 14. 实施顺序

1. 新增 evaluation benchmark，不改线上搜索。
2. 新增 FTS5 sparse index 与 sparse retriever。
3. 新增 QueryPlan 与 retrieval models。
4. 接入 dense retriever 适配层。
5. 接入 RRF fusion。
6. 接入 DashScope reranker provider。
7. 接入 file aggregator。
8. 重写结构化 chunking。
9. 用 benchmark 调整权重与默认模型。
10. 将新链路切为默认搜索路径。

## 15. References

- SQLite FTS5 官方文档：<https://www.sqlite.org/fts5.html>
- Chroma metadata / where filter 官方文档：<https://docs.trychroma.com/docs/querying-collections/metadata-filtering>
- Alibaba Cloud Model Studio embedding 官方文档：<https://www.alibabacloud.com/help/en/model-studio/user-guide/embedding>
- Alibaba Cloud Model Studio text rerank 官方文档：<https://www.alibabacloud.com/help/en/model-studio/text-rerank-api>
