"""测试 Phase 8 依赖审计脚本。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_audit_script_module():
    script_path = Path("scripts/audit_dependencies.py")
    spec = importlib.util.spec_from_file_location("phase8_audit_dependencies", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeDistribution:
    """最小化的 fake distribution。"""

    def __init__(self, name: str, *, requires: list[str] | None = None, top_level: str = ""):
        self.metadata = {"Name": name}
        self.requires = requires or []
        self._top_level = top_level

    def read_text(self, filename: str) -> str | None:
        if filename == "top_level.txt":
            return self._top_level
        return None


class TestPhase8DependencyAuditScript:
    """审计脚本的核心逻辑测试。"""

    def test_find_preferred_python_prefers_project_venv_when_current_differs(self, tmp_path):
        module = _load_audit_script_module()
        project_root = tmp_path / "repo"
        venv_python = project_root / "venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("", encoding="utf-8")

        result = module.find_preferred_python(project_root, tmp_path / "system-python")

        assert result == venv_python

    def test_find_preferred_python_returns_none_when_already_using_venv(self, tmp_path):
        module = _load_audit_script_module()
        project_root = tmp_path / "repo"
        venv_python = project_root / "venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("", encoding="utf-8")

        result = module.find_preferred_python(project_root, venv_python)

        assert result is None

    def test_analyze_candidates_marks_package_removable_when_no_import_and_no_reverse_dep(self):
        module = _load_audit_script_module()

        result = module.analyze_candidates(
            candidates=["build"],
            runtime_modules=["flask"],
            runtime_root_distributions=["flask"],
            reverse_dependencies={},
            base_requirements=["build", "flask"],
            package_to_distribution={"flask": ["Flask"], "build": ["build"]},
        )

        assert result[0]["candidate"] == "build"
        assert result[0]["removable"] is True

    def test_analyze_candidates_keeps_package_when_reverse_dependency_exists(self):
        module = _load_audit_script_module()

        result = module.analyze_candidates(
            candidates=["uvicorn"],
            runtime_modules=["flask"],
            runtime_root_distributions=["flask", "chromadb"],
            reverse_dependencies={"uvicorn": ["chromadb"]},
            base_requirements=["uvicorn", "flask"],
            package_to_distribution={"flask": ["Flask"], "uvicorn": ["uvicorn"]},
        )

        assert result[0]["candidate"] == "uvicorn"
        assert result[0]["removable"] is False
        assert result[0]["required_by"] == ["chromadb"]

    def test_build_package_to_distribution_map_uses_top_level_metadata(self):
        module = _load_audit_script_module()
        fake_dist = FakeDistribution("python-docx", top_level="docx\n")

        mapping = module.build_package_to_distribution_map(
            distributions=[fake_dist],
            package_map={},
        )

        assert mapping["docx"] == ["python-docx"]
