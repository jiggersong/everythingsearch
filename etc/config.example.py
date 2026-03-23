# config.example.py - 配置模板
# 复制到仓库根目录: cp etc/config.example.py config.py

import os


def _project_root() -> str:
    d = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(d) if os.path.basename(d) == "etc" else d


_ROOT = _project_root()

# ================= 必填配置 =================

# 1. 阿里通义千问 API Key（优先从环境变量 DASHSCOPE_API_KEY 读取）
MY_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-your-api-key-here")

# 2. 你想要索引的根目录（支持单个路径或路径列表）
# 单目录: TARGET_DIR = "/path/to/your/documents"
# 多目录: TARGET_DIR = ["/path/to/docs", "/path/to/projects"]
TARGET_DIR = "/path/to/your/documents"

# 只索引路径中包含这些词的文件（空列表 [] 则索引全部）
INDEX_ONLY_KEYWORDS = []

# 3. [可选] 是否启用 MWeb 数据源
# - 不安装 MWeb / 不需要检索 MWeb 内容：请保持 False（推荐）
# - 需要检索 MWeb：设为 True，并配置 MWEB_DIR / MWEB_EXPORT_SCRIPT
ENABLE_MWEB = False

# 4. [可选] MWeb 笔记导出目录与导出脚本（仅在 ENABLE_MWEB=True 时使用）
MWEB_DIR = ""
MWEB_EXPORT_SCRIPT = ""

# [可选] 服务监听地址与端口（用于本地域名等）
# HOST: "127.0.0.1" 仅本机；"0.0.0.0" 允许局域网访问。配合 /etc/hosts 可绑定本地域名
# PORT: 默认 8000；若改为 80 需 root 或反向代理
# HOST = "127.0.0.1"
# PORT = 8000

# [可选] Skills / HTTP 客户端：/api/file/read 单次读取正文的最大字节数（防止一次读入过大文件）
API_MAX_READ_BYTES = 524288

# 增量索引状态数据库
INDEX_STATE_DB = os.path.join(_ROOT, "data", "index_state.db")

# 扫描缓存：未变更文件跳过解析
SCAN_CACHE_PATH = os.path.join(_ROOT, "data", "scan_cache.db")


# ================= 高级配置 =================

PERSIST_DIRECTORY = os.path.join(_ROOT, "data", "chroma_db")
EMBEDDING_MODEL = "text-embedding-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
MAX_CONTENT_LENGTH = 20000
SEARCH_TOP_K = 250
SCORE_THRESHOLD = 0.35
EMBEDDING_CACHE_PATH = os.path.join(_ROOT, "data", "embedding_cache.db")

POSITION_WEIGHTS = {
    "filename": 0.60,
    "heading":  0.80,
    "content":  1.00,
}
KEYWORD_FREQ_BONUS = 0.03

TEXT_EXTENSIONS = {
    '.txt', '.md', '.py', '.js', '.json', '.html', '.css', '.c', '.cpp',
    '.h', '.java', '.go', '.ts', '.vue', '.sql', '.sh', '.yaml', '.xml',
    '.csv', '.log', '.ini', '.cfg', '.toml', '.rst', '.r', '.rb', '.php',
}
OFFICE_EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.pptx'}
MEDIA_EXTENSIONS = {
    '.key', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
    '.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav', '.m4a', '.tiff',
    '.heic', '.flac', '.aac', '.ogg', '.wmv', '.zip', '.rar', '.7z',
    '.dmg', '.iso', '.exe', '.app', '.sketch', '.fig', '.psd', '.ai',
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | OFFICE_EXTENSIONS | MEDIA_EXTENSIONS


def get_target_dirs():
    """Return list of target directories to index."""
    t = TARGET_DIR
    if isinstance(t, (list, tuple)):
        return [str(d).rstrip("/") for d in t if d]
    return [str(t).rstrip("/")] if t else []
