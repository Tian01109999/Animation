"""ffmpeg: ghi khung RGBA thô qua stdin -> mp4 (h264_nvenc, dự phòng libx264), ghép shot, mux âm thanh."""
from __future__ import annotations

import logging
import queue
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

from ..config import get
from .. import tools_bin

log = logging.getLogger("storytoon.render")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


ffmpeg_exe = tools_bin.ffmpeg_exe  # runtime/ffmpeg trước, rồi PATH (xem storytoon/tools_bin.py)


def _codec_args(encoder: str, fps: int) -> list[str]:
    gop = ["-g", str(fps * 2), "-bf", "2"] if encoder == "h264_nvenc" else ["-g", str(fps * 2)]
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "20", "-b:v", "0",
                "-profile:v", "high", "-pix_fmt", "yuv420p", *gop]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p", *gop]


@lru_cache(maxsize=1)
def pick_encoder() -> str:
    """Thử NVENC 1 lần/tiến trình; lỗi -> libx264."""
    want = str(get("render.encoder", "h264_nvenc") or "h264_nvenc")
    if want != "h264_nvenc":
        return "libx264"
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x144:r=30:d=0.2",
           *_codec_args("h264_nvenc", 30), "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=_NO_WINDOW)
        if r.returncode == 0:
            return "h264_nvenc"
        log.warning("NVENC không dùng được (%s) — chuyển sang libx264", r.stderr.decode("utf-8", "ignore").strip()[:200])
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("NVENC không dùng được (%s) — chuyển sang libx264", e)
    return "libx264"


class FrameWriter:
    """Mở ffmpeg, nhận khung RGBA (bytes/memoryview) qua stdin. Ghi pipe ở luồng riêng để song song với render."""

    def __init__(self, out_mp4: Path, width: int, height: int, fps: int, encoder: str | None = None,
                 pix_fmt: str = "rgba") -> None:
        self.out = Path(out_mp4)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.encoder = encoder or pick_encoder()
        self.tmp = self.out.with_suffix(".part.mp4")
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
               *_codec_args(self.encoder, fps), "-r", str(fps), "-movflags", "+faststart", str(self.tmp)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
        self.q: queue.Queue[bytes | None] = queue.Queue(maxsize=4)
        self.err: Exception | None = None
        self.th = threading.Thread(target=self._pump, daemon=True)
        self.th.start()
        self.frames = 0

    def _pump(self) -> None:
        assert self.proc.stdin is not None
        while True:
            buf = self.q.get()
            if buf is None:
                break
            if self.err:
                continue
            try:
                self.proc.stdin.write(buf)
            except OSError as e:
                self.err = e

    def write(self, frame: bytes) -> None:
        if self.err:
            raise RuntimeError(f"ffmpeg dừng bất thường: {self.err}; {self._stderr()}")
        self.q.put(frame)
        self.frames += 1

    def _stderr(self) -> str:
        try:
            return (self.proc.stderr.read() if self.proc.stderr else b"").decode("utf-8", "ignore")[-800:]
        except OSError:
            return ""

    def close(self) -> Path:
        self.q.put(None)
        self.th.join()
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        rc = self.proc.wait()
        if rc != 0 or self.err:
            msg = self._stderr()
            self.tmp.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg ({self.encoder}) lỗi mã {rc}: {msg}")
        self.tmp.replace(self.out)
        return self.out

    def abort(self) -> None:
        try:
            self.proc.kill()
        except OSError:
            pass
        self.tmp.unlink(missing_ok=True)


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg lỗi: " + r.stderr.decode("utf-8", "ignore")[-1200:])


def concat_videos(parts: list[Path], out_mp4: Path, soundtrack: Path | None = None) -> Path:
    """Ghép các mp4 (cùng codec/kích thước) bằng concat demuxer (-c copy), rồi mux âm thanh nếu có."""
    if not parts:
        raise ValueError("Không có shot nào để ghép")
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    lst = out_mp4.with_suffix(".concat.txt")
    lines = []
    for p in parts:
        s = Path(p).resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{s}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp = out_mp4.with_suffix(".part.mp4")
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if soundtrack and Path(soundtrack).exists():
        cmd += ["-i", str(soundtrack), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-shortest"]
    else:
        if soundtrack:
            log.warning("Không thấy file âm thanh %s — xuất phim không tiếng", soundtrack)
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", str(tmp)]
    try:
        _run(cmd)
        tmp.replace(out_mp4)
    finally:
        lst.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    return out_mp4
