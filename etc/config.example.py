# config.example.py - 配置模板
# 复制到仓库根目录: cp etc/config.example.py config.py
# 配置优先级：环境变量 > 仓库根目录 config.py > 代码内安全默认值

import os


def _project_root() -> str:
    d = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(d) if os.path.basename(d) == "etc" else d


_ROOT = _project_root()

# ================= 必填配置 =================

# 1. 阿里通义千问 API Key
# 推荐仅设置环境变量 DASHSCOPE_API_KEY，把这里留空；
# 若你必须把 Key 写入本地 config.py，可直接填写真实值，例如 "sk-xxxx"。
MY_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()

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

# 4. [可选] MWeb 笔记配置（仅在 ENABLE_MWEB=True 时生效）
# MWEB_LIBRARY_PATH: MWeb数据库目录（留空则默认 macOS 标准路径）
# MWEB_DIR: 导出的 Markdown 文件存放地（留空则默认为内置的 data/mweb_export）
MWEB_LIBRARY_PATH = ""
MWEB_DIR = ""

# [可选] 服务监听地址与端口（用于本地域名等）
# HOST: "127.0.0.1" 仅本机；"0.0.0.0" 允许局域网访问。配合 /etc/hosts 可绑定本地域名
# PORT: 默认 8000；若改为 80 需 root 或反向代理
# HOST = "127.0.0.1"
# PORT = 8000

# 说明：
# - DASHSCOPE_API_KEY 环境变量优先于 MY_API_KEY；TARGET_DIR 环境变量优先于 config.py
# - 若 DASHSCOPE_API_KEY / TARGET_DIR 缺失，搜索或索引会显式报错，这是预期行为

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
# 搜索超时秒数；设为 0 表示关闭搜索超时控制，但仍保留单飞执行与繁忙保护
SEARCH_TIMEOUT_SECONDS = 30
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

# ================= 智能对话搜索配置 =================
# 说明：已配置 MY_API_KEY / DASHSCOPE_API_KEY 时，Web 搜索默认走意图识别 + 混合检索；
# 未配置 Key 时前端自动使用普通关键词/语义混合接口。

# 信任前置代理网关获取真实 IP (例如 Nginx 的 X-Forwarded-For)
TRUST_PROXY = False

# 意图识别所用的大模型（推荐用支持 JSON Mode 的模型，如 qwen-turbo）
NL_INTENT_MODEL = "qwen-turbo"

# 解读长文本返回结构的大模型
SEARCH_INTERPRET_MODEL = "qwen-turbo"

# 模型超时时间配置（秒）
NL_TIMEOUT_SEC = 10
INTERPRET_TIMEOUT_SEC = 20


def get_target_dirs():
    """Return list of target directories to index."""
    t = TARGET_DIR
    if isinstance(t, (list, tuple)):
        return [str(d).rstrip("/") for d in t if d]
    return [str(t).rstrip("/")] if t else []
