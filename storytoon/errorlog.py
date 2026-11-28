"""Nhật ký lỗi chung: logs/errors.log trong thư mục app.

Ghi mọi lỗi (logger mức ERROR trở lên, ngoại lệ không bắt trong luồng chính/luồng phụ, lỗi
từng bước pipeline) kèm thời điểm, nơi xảy ra, ngữ cảnh và traceback đầy đủ. Xoay vòng 5 MB × 5 file.

    install()                               # gọi 1 lần khi khởi động (an toàn khi gọi lại)
    record(where, exc, **context)           # ghi 1 lỗi kèm ngữ cảnh (không ghi trùng cùng 1 ngoại lệ)
"""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
import threading
import traceback
from typing import Any

from . import paths

LOG_FILE = paths.LOGS / "errors.log"
_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | luồng %(threadName)s\n%(message)s\n" + "-" * 100
_lock = threading.Lock()
_handler: logging.Handler | None = None
log = logging.getLogger("storytoon.errors")


class _Handler(logging.handlers.RotatingFileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            if getattr(exc, "_storytoon_logged", False) and record.name != log.name:
                return                       # đã ghi chi tiết qua record()
        super().emit(record)


def install() -> logging.Handler | None:
    """Gắn handler ghi errors.log vào root logger + bắt ngoại lệ không xử lý."""
    global _handler
    with _lock:
        if _handler is not None:
            return _handler
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            handler = _Handler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8", delay=True)
        except OSError:
            return None
        handler.setLevel(logging.ERROR)
        handler.setFormatter(logging.Formatter(_FORMAT, "%Y-%m-%d %H:%M:%S"))
        logging.getLogger().addHandler(handler)
        _handler = handler

    previous_hook = sys.excepthook

    def excepthook(kind, value, tb):
        if not issubclass(kind, KeyboardInterrupt):
            log.critical("Lỗi không xử lý trong luồng chính", exc_info=(kind, value, tb))
        previous_hook(kind, value, tb)

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread else "?"
            log.critical("Lỗi không xử lý trong luồng %s", name,
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    original_print_exc = traceback.print_exc

    def print_exc(*args: Any, **kwargs: Any) -> None:
        # Gradio/thư viện in lỗi của thao tác giao diện bằng traceback.print_exc() → ghi lại luôn
        exc = sys.exc_info()[1]
        if exc is not None:
            try:
                record("Thao tác giao diện / thư viện", exc)
            except Exception:  # noqa: BLE001 - ghi log không được làm hỏng luồng lỗi gốc
                pass
        original_print_exc(*args, **kwargs)

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    traceback.print_exc = print_exc
    log.info("errors.log sẵn sàng (Python %s, %s)", platform.python_version(), platform.platform())
    return handler


def record(where: str, exc: BaseException, **context: Any) -> None:
    """Ghi lỗi kèm nơi xảy ra và ngữ cảnh (project, bước, ...). Mỗi ngoại lệ chỉ ghi 1 lần."""
    if getattr(exc, "_storytoon_logged", False):
        return
    install()
    details = "\n".join(f"  {k}: {v}" for k, v in context.items() if v not in (None, ""))
    log.error("Lỗi tại: %s\n  loại: %s\n  thông báo: %s%s", where, type(exc).__name__, exc,
              ("\n" + details) if details else "", exc_info=exc)
    try:
        exc._storytoon_logged = True  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        pass
