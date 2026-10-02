"""P2 运维：结构化日志。

输出 JSON 行，便于采集系统解析；级别与目标可由环境变量配置。
默认级别 INFO，输出到 stderr（与 systemd 一致）。设为 FILE 时写文件并做简单大小轮转（容量控制）。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading

_ENV_LEVEL = "OPTV2_LOG_LEVEL"
_ENV_TARGET = "OPTV2_LOG_TARGET"   # stdout | stderr | file:<path>
_ENV_FILE_MAX = "OPTV2_LOG_FILE_MAX"  # 轮转前最大字节数，默认 10MB


def _rotate_if_needed(path: str, max_bytes: int) -> bool:
    """极简容量控制：超过 max_bytes 时重命名 .1（旧 .1 丢弃）。返回是否轮转。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if size < max_bytes:
        return False
    try:
        os.replace(path, path + ".1")
    except OSError:
        return False
    return True


class _FileHandlerWithRotation(logging.FileHandler):
    def __init__(self, path: str, **kw):
        super().__init__(path, **kw)
        self._lock = threading.Lock()

    def emit(self, record):
        with self._lock:
            max_bytes = int(os.environ.get(_ENV_FILE_MAX, 10 * 1024 * 1024))
            rotated = _rotate_if_needed(self.baseFilename, max_bytes)
            if rotated:
                # 旧文件已改名，重开同名流，后续写入落到新文件
                self.close()
                self.stream = self._open()
            super().emit(record)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        obj = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


def setup_logging(level_name: str | None = None, target: str | None = None) -> logging.Logger:
    """配置根日志器。level_name/target 为 None 时取环境变量，否则用默认。幂等可重入。"""
    lvl_name = level_name or os.environ.get(_ENV_LEVEL, "INFO").upper()
    tgt = target or os.environ.get(_ENV_TARGET, "stderr")
    level = getattr(logging, lvl_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # 移除既有 handler，避免重复输出（重入安全）
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = JsonFormatter()

    if tgt.startswith("file:"):
        path = tgt[len("file:"):]
        handler = _FileHandlerWithRotation(path, mode="a", encoding="utf-8")
    elif tgt == "stdout":
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.propagate = False

    # 抑制第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(max(level, logging.WARNING))
    logging.getLogger("httpx").setLevel(max(level, logging.WARNING))
    return root


def get_logger(name: str = "option-v2") -> logging.Logger:
    return logging.getLogger(name)
