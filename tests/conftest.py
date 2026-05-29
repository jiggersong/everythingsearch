import os
import sys
from pathlib import Path

import config

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

_TEST_DATA_DIR = f"/tmp/everythingsearch-test-{os.getpid()}"

config.MY_API_KEY = "dummy-key-for-tests"
# DashScope/langchain 父类仍读取 DASHSCOPE_API_KEY 环境变量（SDK 适配，非业务配置来源）
os.environ["DASHSCOPE_API_KEY"] = config.MY_API_KEY
config.PERSIST_DIRECTORY = f"{_TEST_DATA_DIR}/chroma_db"
config.SPARSE_INDEX_PATH = f"{_TEST_DATA_DIR}/sparse_index.db"
config.INDEX_STATE_DB = f"{_TEST_DATA_DIR}/index_state.db"
config.SCAN_CACHE_PATH = f"{_TEST_DATA_DIR}/scan_cache.db"
config.EMBEDDING_CACHE_PATH = f"{_TEST_DATA_DIR}/embedding_cache.db"
config.MWEB_DIR = f"{_TEST_DATA_DIR}/mweb_export"
