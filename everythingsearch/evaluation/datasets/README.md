# Search Evaluation Datasets

Place local JSONL evaluation datasets in this directory.

Each non-empty line must be a JSON object:

```json
{
  "query": "季度预算 excel",
  "query_type": "hybrid",
  "relevant_files": [
    {"filepath": "/absolute/path/to/budget.xlsx", "grade": 3}
  ],
  "must_include": [],
  "notes": "预算主题查询"
}
```

Grades:

- `3`: ideal result
- `2`: highly relevant
- `1`: acceptable
- `0`: not relevant

Each line must include **at least one** `relevant_files` entry with `grade > 0`.

The `must_include` field is reserved for future constraint metrics; the current runner does not score it.

Run:

```bash
python -m everythingsearch.evaluation.benchmark_runner everythingsearch/evaluation/datasets/search_eval.jsonl
```
