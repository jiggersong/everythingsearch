import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_VENV_DIR = (_PROJECT_ROOT / "venv").resolve()
_ACTUAL_PREFIX = Path(sys.prefix).resolve()
_ACTUAL_PYTHON = Path(sys.executable).resolve()

if _ACTUAL_PREFIX != _EXPECTED_VENV_DIR:
    raise RuntimeError(
        "测试必须使用项目虚拟环境解释器运行。"
        f"当前 sys.prefix: {_ACTUAL_PREFIX}；"
        f"当前解释器: {_ACTUAL_PYTHON}；"
        f"期望 venv: {_EXPECTED_VENV_DIR}。"
        "请改用 ./venv/bin/pytest。"
    )

os.environ["DASHSCOPE_API_KEY"] = "dummy-key-for-tests"
os.environ["API_INDEX_DIR"] = "/tmp/dummy-index"
os.environ["API_CHROMA_DIR"] = "/tmp/dummy-chroma"
_TEST_DATA_DIR = f"/tmp/everythingsearch-test-{os.getpid()}"
os.environ["PERSIST_DIRECTORY"] = f"{_TEST_DATA_DIR}/chroma_db"
os.environ["SPARSE_INDEX_PATH"] = f"{_TEST_DATA_DIR}/sparse_index.db"
os.environ["INDEX_STATE_DB"] = f"{_TEST_DATA_DIR}/index_state.db"
os.environ["SCAN_CACHE_PATH"] = f"{_TEST_DATA_DIR}/scan_cache.db"
os.environ["EMBEDDING_CACHE_PATH"] = f"{_TEST_DATA_DIR}/embedding_cache.db"
os.environ["MWEB_DIR"] = f"{_TEST_DATA_DIR}/mweb_export"
