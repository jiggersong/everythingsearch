from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _load_config(config_path: Path):
    spec = importlib.util.spec_from_file_location("upgraded_config", config_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_script_keeps_backup_in_target_and_migrates_string_target_dir(tmp_path: Path) -> None:
    """验证升级脚本能安全迁移旧配置、备份数据，并更新运行时依赖。"""
    if shutil.which("rsync") is None:
        pytest.skip("upgrade.sh 依赖 rsync")

    new_root = tmp_path / "EverythingSearch-new"
    old_root = tmp_path / "EverythingSearch-old"
    fake_bin = tmp_path / "fake-bin"
    pip_log = tmp_path / "pip-args.log"

    (new_root / "scripts").mkdir(parents=True)
    (new_root / "etc").mkdir()
    (new_root / "everythingsearch").mkdir()
    (new_root / "requirements").mkdir()
    fake_bin.mkdir()

    shutil.copy2(PROJECT_ROOT / "scripts" / "upgrade.sh", new_root / "scripts" / "upgrade.sh")
    (new_root / "scripts" / "upgrade.sh").chmod(0o755)
    _write_executable(
        new_root / "scripts" / "install_launchd_wrappers.sh",
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$1/launchd_update_path.txt\"\n",
    )
    (new_root / "etc" / "config.example.py").write_text(
        "\n".join(
            [
                'MY_API_KEY = ""',
                'TARGET_DIR = "/path/to/your/documents"',
                "ENABLE_MWEB = False",
                'MWEB_LIBRARY_PATH = ""',
                'MWEB_DIR = ""',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (new_root / "everythingsearch" / "__init__.py").write_text("", encoding="utf-8")
    (new_root / "requirements" / "base.txt").write_text("click==8.3.1\n", encoding="utf-8")

    (old_root / "data" / "chroma_db").mkdir(parents=True)
    (old_root / "venv" / "bin").mkdir(parents=True)
    (old_root / "config.py").write_text(
        "\n".join(
            [
                'MY_API_KEY = "sk-test"',
                'TARGET_DIR = "/Users/example/Documents"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (old_root / "data" / "embedding_cache.db").write_text("cache", encoding="utf-8")
    (old_root / "data" / "chroma_db" / "marker.txt").write_text("vector", encoding="utf-8")
    (old_root / "data" / "scan_cache.db").write_text("scan", encoding="utf-8")
    _write_executable(
        old_root / "venv" / "bin" / "python",
        "#!/usr/bin/env bash\n"
        f"echo \"$@\" >> \"{pip_log}\"\n"
        "exit 0\n",
    )

    _write_executable(fake_bin / "uname", "#!/usr/bin/env bash\necho Darwin\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    completed = subprocess.run(
        [str(new_root / "scripts" / "upgrade.sh"), str(old_root)],
        input="\n\nn\n",
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not list(new_root.glob("upgrade_backups_*"))

    backup_dirs = list(old_root.glob("upgrade_backups_*"))
    assert len(backup_dirs) == 1
    backup_dir = backup_dirs[0]
    assert (backup_dir / "config.py").exists()
    assert (backup_dir / "embedding_cache.db").read_text(encoding="utf-8") == "cache"
    assert (backup_dir / "chroma_db" / "marker.txt").read_text(encoding="utf-8") == "vector"

    upgraded_config = _load_config(old_root / "config.py")
    assert upgraded_config.MY_API_KEY == "sk-test"
    assert upgraded_config.TARGET_DIR == "/Users/example/Documents"
    assert upgraded_config.ENABLE_MWEB is False

    assert not (old_root / "data" / "chroma_db").exists()
    assert not (old_root / "data" / "scan_cache.db").exists()
    assert (old_root / "launchd_update_path.txt").read_text(encoding="utf-8").strip() == str(old_root)

    pip_args = pip_log.read_text(encoding="utf-8")
    assert "-m pip install -r" in pip_args
    assert str(old_root / "requirements" / "base.txt") in pip_args


def test_install_launchd_wrappers_uses_existing_dotvenv_python(tmp_path: Path) -> None:
    """验证 launchd wrapper 不会在只有 .venv 时写死 venv/bin/python。"""
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

    app_wrapper = fake_home / ".local" / "bin" / "everythingsearch_start.sh"
    index_wrapper = fake_home / ".local" / "bin" / "everythingsearch_index.sh"
    app_content = app_wrapper.read_text(encoding="utf-8")
    index_content = index_wrapper.read_text(encoding="utf-8")
    assert f'PYTHON_BIN="{python_path}"' in app_content
    assert f'PYTHON_BIN="{python_path}"' in index_content
    assert "$APP_DIR/venv/bin/python" not in app_content
    assert "$APP_DIR/venv/bin/python" not in index_content
