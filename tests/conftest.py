import os

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
