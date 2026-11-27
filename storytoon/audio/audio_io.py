"""Tiện ích I/O âm thanh dùng chung: ffmpeg, đọc/ghi wav, giải mã sang float32.

Mọi đường dẫn là pathlib.Path; truyền cho ffmpeg dưới dạng str (CreateProcessW xử lý Unicode tốt,
kể cả "Làm việc").
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from .. import tools_bin

SR = 48000  # sample rate chuẩn của toàn bộ pipeline âm thanh

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


ffmpeg_exe = tools_bin.ffmpeg_exe  # runtime/ffmpeg/ffmpeg.exe nếu có, không thì ffmpeg trong PATH


def run_ffmpeg(args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    """Chạy ffmpeg (đã thêm -hide_banner -loglevel error -y). Trả về stdout; lỗi -> RuntimeError."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, input=input_bytes, capture_output=True, creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"ffmpeg lỗi (mã {proc.returncode}): {err[-800:]}")
    return proc.stdout


def to_wav(src: Path, dst: Path, *, sr: int = SR, channels: int = 1) -> Path:
    """Chuyển bất kỳ file âm thanh nào sang wav PCM16."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".part.wav")
    run_ffmpeg(["-i", str(src), "-ac", str(channels), "-ar", str(sr), "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(dst)
    return dst


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Đọc wav PCM16 -> (float32 [n, ch], sr). Chỉ cho wav do chính module này ghi."""
    with wave.open(str(path), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        return decode(path, sr=sr, channels=ch), sr
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return data.reshape(-1, ch), sr


def decode(path: Path, *, sr: int = SR, channels: int = 2) -> np.ndarray:
    """Giải mã mọi định dạng (mp3/ogg/flac/wav/m4a) -> float32 [n, channels] qua ffmpeg."""
    raw = run_ffmpeg(["-i", str(path), "-f", "f32le", "-acodec", "pcm_f32le",
                      "-ac", str(channels), "-ar", str(sr), "-"])
    return np.frombuffer(raw, dtype="<f4").reshape(-1, channels).copy()


def write_wav(path: Path, data: np.ndarray, sr: int = SR) -> Path:
    """Ghi float32 [n] hoặc [n, ch] ra wav PCM16 (clip về [-1, 1])."""
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[:, None]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".part.wav")
    step = 1 << 19   # ghi theo khúc: phim dài không cần thêm vài trăm MB RAM cho bản PCM
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(arr.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        for a in range(0, max(1, len(arr)), step):
            pcm = (np.clip(arr[a: a + step], -1.0, 1.0) * 32767.0).astype("<i2")
            w.writeframes(pcm.tobytes())
    tmp.replace(path)
    return path


def encode(src_wav: Path, dst: Path) -> Path:
    """Nén wav sang định dạng theo đuôi dst (.ogg -> vorbis, .mp3 -> lame)."""
    codec = {".ogg": ["-c:a", "libvorbis", "-q:a", "5"], ".mp3": ["-c:a", "libmp3lame", "-q:a", "3"]}
    run_ffmpeg(["-i", str(src_wav), *codec.get(dst.suffix.lower(), []), str(dst)])
    return dst
