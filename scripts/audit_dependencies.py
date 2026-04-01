#!/usr/bin/env python3
"""依赖审计脚本。

输出仓库运行时直接 import、候选包反向依赖与是否建议继续保留的基线信息。
默认输出可读文本；传入 ``--json`` 可输出 JSON。
"""

from __future__ import annotations

import argparse
import ast
import json
from importlib import metadata
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

DEFAULT_CANDIDATES = (
    "kubernetes",
    "langgraph",
    "langgraph-checkpoint",
    "langgraph-prebuilt",
    "langgraph-sdk",
    "langsmith",
    "uvicorn",
    "uvloop",
    "watchfiles",
    "bcrypt",
    "cryptography",
    "pillow",
    "xlsxwriter",
    "websockets",
    "websocket-client",
    "lxml",
)

_LOCAL_IMPORT_ROOTS = {
    "__future__",
    "everythingsearch",
    "tests",
    "infra",
    "services",
    "file_access",
    "request_validation",
    "logging_config",
    "embedding_cache",
    "paths",
    "search",
    "search_service",
}
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+")
_REEXEC_ENV_KEY = "EVERYTHINGSEARCH_AUDIT_REEXEC"


def _normalize_dist_name(name: str) -> str:
    return name.lower().replace("_", "-")


def collect_runtime_import_modules(package_root: Path) -> list[str]:
    """收集运行代码中的三方顶级 import 模块名。"""
    imports: set[str] = set()
    stdlib = set(sys.stdlib_module_names)
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

    filtered = {
        name
        for name in imports
        if name not in stdlib and name not in _LOCAL_IMPORT_ROOTS
    }
    return sorted(filtered)


def build_package_to_distribution_map(
    distributions: list[metadata.Distribution] | None = None,
    package_map: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """构建顶级包到分发名的映射。"""
    mapping = {
        package: list(dist_names)
        for package, dist_names in (package_map or metadata.packages_distributions()).items()
    }
    for dist in distributions or list(metadata.distributions()):
        dist_name = dist.metadata.get("Name")
        if not dist_name:
            continue
        top_level = dist.read_text("top_level.txt") or ""
        for line in top_level.splitlines():
            package = line.strip()
            if not package:
                continue
            mapping.setdefault(package, [])
            if dist_name not in mapping[package]:
                mapping[package].append(dist_name)
    return mapping


def collect_runtime_root_distributions(
    runtime_modules: list[str],
    package_to_distribution: dict[str, list[str]],
) -> list[str]:
    """收集运行代码直接 import 对应的分发名。"""
    runtime_roots: set[str] = set()
    for module_name in runtime_modules:
        for dist_name in package_to_distribution.get(module_name, []):
            runtime_roots.add(_normalize_dist_name(dist_name))
    return sorted(runtime_roots)


def build_reverse_dependency_map(
    distributions: list[metadata.Distribution] | None = None,
) -> dict[str, list[str]]:
    """构建分发名到反向依赖列表的映射。"""
    reverse: dict[str, set[str]] = {}
    for dist in distributions or list(metadata.distributions()):
        depender_name = dist.metadata.get("Name")
        if not depender_name:
            continue
        for req_line in dist.requires or []:
            requirement = req_line.split(";", 1)[0].strip()
            if not requirement:
                continue
            match = _NAME_RE.match(requirement)
            if not match:
                continue
            dependency_name = _normalize_dist_name(match.group(0))
            reverse.setdefault(dependency_name, set()).add(depender_name)
    return {
        dependency_name: sorted(depender_names)
        for dependency_name, depender_names in reverse.items()
    }


def read_requirement_names(requirements_path: Path) -> list[str]:
    """读取 requirements 文件中的一级依赖名。"""
    names: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
            continue
        names.append(_normalize_dist_name(stripped.split("==", 1)[0].strip()))
    return names


def analyze_candidates(
    *,
    candidates: list[str],
    runtime_modules: list[str],
    runtime_root_distributions: list[str],
    reverse_dependencies: dict[str, list[str]],
    base_requirements: list[str],
    package_to_distribution: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """分析候选依赖当前是否具备移除条件。"""
    runtime_module_set = set(runtime_modules)
    runtime_root_set = set(runtime_root_distributions)
    base_requirement_set = set(base_requirements)
    analyzed: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_name = _normalize_dist_name(candidate)
        top_level_modules = sorted(
            package
            for package, dist_names in package_to_distribution.items()
            if any(_normalize_dist_name(dist_name) == normalized_name for dist_name in dist_names)
        )
        direct_modules = sorted(runtime_module_set & set(top_level_modules))
        required_by = reverse_dependencies.get(normalized_name, [])
        in_runtime_roots = normalized_name in runtime_root_set
        in_base_requirements = normalized_name in base_requirement_set
        removable = (
            in_base_requirements
            and not direct_modules
            and not required_by
            and not in_runtime_roots
        )
        analyzed.append(
            {
                "candidate": candidate,
                "normalized_name": normalized_name,
                "top_level_modules": top_level_modules,
                "direct_import_modules": direct_modules,
                "required_by": required_by,
                "in_runtime_roots": in_runtime_roots,
                "in_base_requirements": in_base_requirements,
                "removable": removable,
            }
        )
    return analyzed


def build_audit_report(
    *,
    package_root: Path,
    base_requirements_path: Path,
    candidates: list[str],
) -> dict[str, Any]:
    """构建完整依赖审计报告。"""
    distributions = list(metadata.distributions())
    package_to_distribution = build_package_to_distribution_map(distributions=distributions)
    runtime_modules = collect_runtime_import_modules(package_root)
    runtime_root_distributions = collect_runtime_root_distributions(
        runtime_modules,
        package_to_distribution,
    )
    reverse_dependencies = build_reverse_dependency_map(distributions=distributions)
    base_requirements = read_requirement_names(base_requirements_path)
    candidates_report = analyze_candidates(
        candidates=candidates,
        runtime_modules=runtime_modules,
        runtime_root_distributions=runtime_root_distributions,
        reverse_dependencies=reverse_dependencies,
        base_requirements=base_requirements,
        package_to_distribution=package_to_distribution,
    )
    return {
        "package_root": str(package_root),
        "base_requirements_path": str(base_requirements_path),
        "runtime_modules": runtime_modules,
        "runtime_root_distributions": runtime_root_distributions,
        "candidates": candidates_report,
    }


def find_preferred_python(project_root: Path, current_executable: Path) -> Path | None:
    """优先返回项目虚拟环境 Python，避免系统解释器缺少完整依赖元数据。"""
    venv_python = project_root / "venv" / "bin" / "python"
    if not venv_python.exists():
        return None
    try:
        if venv_python.resolve() == current_executable.resolve():
            return None
    except FileNotFoundError:
        return None
    return venv_python


def maybe_reexec_with_project_venv(argv: list[str]) -> int | None:
    """如当前不在项目 venv 中，则优先切到项目虚拟环境重新执行。"""
    if os.environ.get(_REEXEC_ENV_KEY):
        return None

    project_root = Path(__file__).resolve().parents[1]
    preferred_python = find_preferred_python(project_root, Path(sys.executable))
    if preferred_python is None:
        return None

    env = dict(os.environ)
    env[_REEXEC_ENV_KEY] = "1"
    completed = subprocess.run([str(preferred_python), *argv], env=env, check=False)
    return completed.returncode


def _format_report_text(report: dict[str, Any]) -> str:
    lines = []
    lines.append("运行时直接 import 模块:")
    for module_name in report["runtime_modules"]:
        lines.append(f"- {module_name}")
    lines.append("")
    lines.append("运行时根分发:")
    for dist_name in report["runtime_root_distributions"]:
        lines.append(f"- {dist_name}")
    lines.append("")
    lines.append("候选依赖审计:")
    for item in report["candidates"]:
        lines.append(f"- {item['candidate']}")
        lines.append(f"  in_base_requirements: {item['in_base_requirements']}")
        lines.append(f"  direct_import_modules: {item['direct_import_modules']}")
        lines.append(f"  required_by: {item['required_by']}")
        lines.append(f"  in_runtime_roots: {item['in_runtime_roots']}")
        lines.append(f"  removable: {item['removable']}")
    return "\n".join(lines)


def main() -> int:
    """脚本入口。"""
    reexec_code = maybe_reexec_with_project_venv(sys.argv)
    if reexec_code is not None:
        return reexec_code

    parser = argparse.ArgumentParser(description="审计 EverythingSearch 依赖使用情况")
    parser.add_argument(
        "--package-root",
        default="everythingsearch",
        help="运行时代码根目录，默认 everythingsearch",
    )
    parser.add_argument(
        "--base-requirements",
        default="requirements/base.txt",
        help="运行时依赖清单路径，默认 requirements/base.txt",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="追加候选包；未提供时使用内置候选列表",
    )
    args = parser.parse_args()

    report = build_audit_report(
        package_root=Path(args.package_root),
        base_requirements_path=Path(args.base_requirements),
        candidates=args.candidate or list(DEFAULT_CANDIDATES),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_report_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
