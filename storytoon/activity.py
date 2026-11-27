"""Track UI work so the desktop shell can protect a running render on close."""
from contextlib import contextmanager
import threading
from collections.abc import Iterator

_lock = threading.Lock()
_running = 0


@contextmanager
def work() -> Iterator[None]:
    global _running
    with _lock:
        _running += 1
    try:
        yield
    finally:
        with _lock:
            _running -= 1


def busy() -> bool:
    with _lock:
        return _running > 0


@contextmanager
def idle_operation() -> Iterator[None]:
    """Keep new work from starting during a short destructive operation."""
    with _lock:
        if _running:
            raise RuntimeError('App đang xử lý. Hãy đợi tác vụ hoàn tất trước khi xóa project.')
        yield
