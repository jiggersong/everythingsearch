"""launchd wrapper 安装脚本测试。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_install_launchd_wrappers_uses_existing_dotvenv_python(tmp_path: Path) -> None:
    """验证 launchd 仓内 wrapper 在仅有 .venv 时使用其 Python，而非写死 venv/bin/python。"""
    project_root = tmp_path / "project"
    fake_home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    launchctl_log = tmp_path / "launchctl.log"
    python_path = project_root / ".venv" / "bin" / "python"

    python_path.parent.mkdir(parents=True)
    fake_home.mkdir()
    fake_bin.mkdir()
    _write_executable(python_path, "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_bin / "launchctl",
        "#!/usr/bin/env bash\n"
        f"echo \"$@\" >> \"{launchctl_log}\"\n"
        "exit 0\n",
    )
    (project_root / "config.py").write_text(
        'HOST = "127.0.0.1"\nPORT = 8000\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    completed = subprocess.run(
        [str(PROJECT_ROOT / "scripts" / "install_launchd_wrappers.sh"), str(project_root)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr

    app_wrapper = project_root / "scripts" / "launchd_app_wrapper.sh"
    index_wrapper = project_root / "scripts" / "launchd_index_wrapper.sh"
    app_content = app_wrapper.read_text(encoding="utf-8")
    index_content = index_wrapper.read_text(encoding="utf-8")
    assert str(python_path) in app_content
    assert str(python_path) in index_content
    assert "$APP_DIR/venv/bin/python" not in app_content
    assert "$APP_DIR/venv/bin/python" not in index_content
