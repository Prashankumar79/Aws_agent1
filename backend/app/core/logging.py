"""Centralized logging configuration with rotation."""

# 🟢 BEGINNER: Standard-library logging plus a rotating file handler so app.log
# never grows past ~50 MB even if the server runs for months.
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os


# 🟢 BEGINNER: Read LOG_LEVEL from the environment so you can crank verbosity to DEBUG
# without changing any code (e.g. `LOG_LEVEL=DEBUG python run.py`).
_DEFAULT_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(level: str = _DEFAULT_LEVEL) -> logging.Logger:
    """Configure root logger with stdout + rotating file handler.

    🟢 BEGINNER: Idempotent means calling this twice is safe — we strip any
    pre-existing handlers first so uvicorn's --reload feature doesn't end up
    printing every log line two or three times.

    Rotation: 10 MB per file, keep 5 backups (≈50 MB ceiling on disk).
    """
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # 🟢 BEGINNER: The "root" logger is the parent of every other logger.
    # Configure it once and every getLogger(__name__) inherits the settings.
    root = logging.getLogger()
    root.setLevel(level)

    # 🟢 BEGINNER: Drop pre-existing handlers (avoids duplicate log lines on uvicorn --reload).
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(_FORMAT)

    # 🟢 BEGINNER: Stdout handler — captured by uvicorn / Docker / k8s log collectors.
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # 🟢 BEGINNER: Rotating file handler — when app.log hits 10 MB it gets renamed
    # to app.log.1, .2, .3, .4, .5 and a fresh app.log starts. Old files are deleted.
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # 🟢 BEGINNER: AWS / HTTP libraries are extremely chatty at INFO level.
    # In production we silence them unless DEBUG is on, otherwise app.log fills with junk.
    if level not in ("DEBUG",):
        for noisy in ("botocore", "urllib3", "httpx", "httpcore", "boto3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger(__name__)


# 🟢 BEGINNER: We deliberately do NOT call setup_logging() at import-time.
# main.py calls it explicitly so tests / scripts can configure their own logging.
