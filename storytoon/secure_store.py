"""Small Windows DPAPI store; secrets stay outside the portable folder."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def protect(value: bytes, *, decrypt: bool = False) -> bytes:
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p if decrypt else ctypes.c_wchar_p,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    result = _Blob()
    if not fn(ctypes.byref(source), None if decrypt else 'StoryToon account', None, None, None, 1, ctypes.byref(result)):
        raise OSError('Không mở được kho tài khoản Windows.')
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)


def store_path(name: str) -> Path:
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local'))) / 'StoryToon' / name


def read(name: str) -> dict:
    path = store_path(name)
    if not path.exists():
        return {}
    value = json.loads(protect(path.read_bytes(), decrypt=True))
    if not isinstance(value, dict):
        raise ValueError('Kho tài khoản không hợp lệ.')
    return value


def write(name: str, value: dict) -> None:
    path = store_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = protect(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def remove(name: str) -> None:
    store_path(name).unlink(missing_ok=True)
