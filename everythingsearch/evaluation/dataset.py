"""检索评测数据集加载与校验。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal


class EvaluationDatasetError(ValueError):
    """评测数据集格式错误。"""


@dataclass(frozen=True)
class RelevantFile:
    """单个相关文件标注。"""

    filepath: str
    grade: int


@dataclass(frozen=True)
class EvaluationCase:
    """单条检索评测用例。"""

    query: str
    query_type: Literal["exact", "semantic", "hybrid", "filename", "code"]
    relevant_files: tuple[RelevantFile, ...]
    must_include: tuple[str, ...]
    notes: str

    @property
    def relevance_by_filepath(self) -> dict[str, int]:
        """返回 filepath -> grade 映射。"""
        return {item.filepath: item.grade for item in self.relevant_files}


def load_evaluation_cases(dataset_path: str | Path) -> list[EvaluationCase]:
    """从 JSONL 文件加载检索评测用例。"""
    path = Path(dataset_path)
    if not path.exists():
        raise EvaluationDatasetError(f"评测数据集不存在: {path}")
    if not path.is_file():
        raise EvaluationDatasetError(f"评测数据集不是文件: {path}")

    cases: list[EvaluationCase] = []
    with path.open("r", encoding="utf-8") as dataset_file:
        for line_number, raw_line in enumerate(dataset_file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvaluationDatasetError(
                    f"第 {line_number} 行不是合法 JSON: {exc.msg}"
                ) from exc
            cases.append(_parse_case(payload, line_number))

    if not cases:
        raise EvaluationDatasetError("评测数据集为空")
    return cases


def _parse_case(payload: Any, line_number: int) -> EvaluationCase:
    if not isinstance(payload, dict):
        raise EvaluationDatasetError(f"第 {line_number} 行必须是 JSON 对象")

    query = _required_str(payload, "query", line_number)
    query_type = _parse_query_type(payload.get("query_type", "hybrid"), line_number)
    relevant_files = _parse_relevant_files(payload.get("relevant_files"), line_number)
    must_include = _parse_str_tuple(payload.get("must_include", []), "must_include", line_number)
    notes = _optional_str(payload.get("notes", ""), "notes", line_number)

    if not any(item.grade > 0 for item in relevant_files):
        raise EvaluationDatasetError(
            f"第 {line_number} 行 relevant_files 须至少包含一条 grade > 0 的标注"
        )

    return EvaluationCase(
        query=query,
        query_type=query_type,
        relevant_files=relevant_files,
        must_include=must_include,
        notes=notes,
    )


def _required_str(payload: dict[str, Any], field_name: str, line_number: int) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDatasetError(f"第 {line_number} 行 {field_name} 必须是非空字符串")
    return value.strip()


def _optional_str(value: Any, field_name: str, line_number: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EvaluationDatasetError(f"第 {line_number} 行 {field_name} 必须是字符串")
    return value.strip()


def _parse_query_type(value: Any, line_number: int) -> Literal["exact", "semantic", "hybrid", "filename", "code"]:
    if value not in {"exact", "semantic", "hybrid", "filename", "code"}:
        raise EvaluationDatasetError(
            f"第 {line_number} 行 query_type 仅支持 exact、semantic、hybrid、filename、code"
        )
    return value


def _parse_relevant_files(value: Any, line_number: int) -> tuple[RelevantFile, ...]:
    if not isinstance(value, list) or not value:
        raise EvaluationDatasetError(f"第 {line_number} 行 relevant_files 必须是非空数组")

    parsed: list[RelevantFile] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EvaluationDatasetError(
                f"第 {line_number} 行 relevant_files[{index}] 必须是对象"
            )
        filepath = item.get("filepath")
        grade = item.get("grade")
        if not isinstance(filepath, str) or not filepath.strip():
            raise EvaluationDatasetError(
                f"第 {line_number} 行 relevant_files[{index}].filepath 必须是非空字符串"
            )
        if filepath in seen:
            raise EvaluationDatasetError(
                f"第 {line_number} 行 relevant_files 存在重复 filepath: {filepath}"
            )
        if not isinstance(grade, int) or grade < 0 or grade > 3:
            raise EvaluationDatasetError(
                f"第 {line_number} 行 relevant_files[{index}].grade 必须是 0..3 整数"
            )
        seen.add(filepath)
        parsed.append(RelevantFile(filepath=filepath.strip(), grade=grade))
    return tuple(parsed)


def _parse_str_tuple(value: Any, field_name: str, line_number: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EvaluationDatasetError(f"第 {line_number} 行 {field_name} 必须是数组")
    parsed: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise EvaluationDatasetError(
                f"第 {line_number} 行 {field_name}[{index}] 必须是字符串"
            )
        stripped = item.strip()
        if stripped:
            parsed.append(stripped)
    return tuple(parsed)

