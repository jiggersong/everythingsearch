# Gunicorn: bind/workers + 按天滚动日志（午夜切分，归档文件带日期后缀如 app.log.2025-03-23）。
import logging
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.join(_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

def _service_bind() -> str:
    try:
        import config as _config
        host = getattr(_config, "HOST", "127.0.0.1")
        port = getattr(_config, "PORT", 8000)
    except ImportError:
        host, port = "127.0.0.1", 8000
    return f"{host}:{port}"


bind = _service_bind()
workers = 1
timeout = 120
worker_class = "sync"

# 由下方 logconfig_dict 接管；勿再传 --access-logfile / --error-logfile。
accesslog = None

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "class": "logging.Formatter",
        },
        "access": {
            "format": "%(message)s",
            "class": "logging.Formatter",
        },
    },
    "handlers": {
        "error_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "generic",
            "filename": os.path.join(_LOG_DIR, "app_err.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": 90,
            "encoding": "utf-8",
            "delay": True,
        },
        "access_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "access",
            "filename": os.path.join(_LOG_DIR, "app.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": 90,
            "encoding": "utf-8",
            "delay": True,
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_file"],
            "propagate": False,
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["access_file"],
            "propagate": False,
        },
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console"],
    },
}


def worker_exit(server, worker):
    """Worker 退出时释放搜索管线线程池，避免线程泄漏。

    SearchPipeline 持有进程级共享的 ThreadPoolExecutor；在 sync worker 退出时
    显式 shutdown，确保搜索线程随进程干净回收（Flask dev server 等非 Gunicorn
    场景也会在解释器退出时随线程自然结束，无需此钩子）。
    """
    try:
        from everythingsearch.app import search_service

        search_service.shutdown_pipeline(wait=False)
    except Exception:  # pragma: no cover - 关闭失败不应阻塞 worker 退出
        logging.exception("worker_exit: failed to shut down search pipeline")
