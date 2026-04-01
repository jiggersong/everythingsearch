"""Phase 8 依赖审计护栏测试。"""

from __future__ import annotations

import ast
from pathlib import Path


_RUNTIME_CANDIDATE_IMPORTS = {
    "kubernetes",
    "langgraph",
    "langsmith",
    "uvicorn",
    "uvloop",
    "watchfiles",
    "bcrypt",
    "cryptography",
    "PIL",
    "xlsxwriter",
    "websockets",
    "websocket",
    "lxml",
}


def _collect_top_level_imports(root: Path) -> set[str]:
    imports: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    return imports


def _read_lines(path: Path) -> list[str]:
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]


class TestPhase8DependencyAudit:
    """锁定首轮候选包当前无直接 import 的事实。"""

    def test_runtime_candidate_packages_have_no_direct_imports(self):
        runtime_imports = _collect_top_level_imports(Path("everythingsearch"))

        unexpected = sorted(runtime_imports & _RUNTIME_CANDIDATE_IMPORTS)

        assert unexpected == []

    def test_requirements_are_split_with_legacy_wrapper(self):
        base_lines = _read_lines(Path("requirements/base.txt"))
        dev_lines = _read_lines(Path("requirements/dev.txt"))
        root_lines = _read_lines(Path("requirements.txt"))

        assert any(line.startswith("Flask==") for line in base_lines)
        assert any(line.startswith("chromadb==") for line in base_lines)
        assert "-r base.txt" in dev_lines
        assert any(line.startswith("pytest==") for line in dev_lines)
        assert "-r requirements/dev.txt" in root_lines

    def test_first_removed_packages_are_absent_from_base_requirements(self):
        base_lines = _read_lines(Path("requirements/base.txt"))

        assert not any(line.startswith("build==") for line in base_lines)
        assert not any(line.startswith("pyproject_hooks==") for line in base_lines)

    def test_scripts_follow_split_requirements_layout(self):
        install_script = Path("scripts/install.sh").read_text(encoding="utf-8")
        test_script = Path("scripts/run_tests.sh").read_text(encoding="utf-8")

        assert "pip install -r requirements/base.txt" in install_script
        assert "pip install -r requirements/dev.txt" in test_script
