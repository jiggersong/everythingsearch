# Gunicorn: bind/workers + 按天滚动日志（午夜切分，归档文件带日期后缀如 app.log.2025-03-23）。
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.join(_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

bind = "127.0.0.1:{}".format(os.environ.get("PORT", "8000"))
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
