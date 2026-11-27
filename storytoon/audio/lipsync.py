"""Lip sync: wav -> danh sách viseme (thời điểm, hình miệng A..H/X).

Hình miệng theo chuẩn Rhubarb / Preston Blair:
    A  khép môi (M, B, P)        B  hé, thấy răng (K, S, T, EE...)   C  mở vừa (EH, AE)
    D  mở rộng (AA)              E  tròn hơi mở (AO, ER)             F  chu môi (UW, OW, W)
    G  răng chạm môi dưới (F, V) H  lưỡi (L)                         X  nghỉ / im lặng

Chiến lược:
1. Rhubarb Lip Sync (runtime/rhubarb) với recognizer "phonetic" — độc lập ngôn ngữ, hợp tiếng Việt.
   KHÔNG truyền --dialogFile: dialog chỉ có tác dụng với recognizer pocketSphinx (tiếng Anh); với
   phonetic, Rhubarb bỏ qua nó, còn với pocketSphinx thì từ tiếng Việt toàn là từ "lạ" -> kết quả kém hơn.
2. Fallback theo biên độ (RMS 30 fps, làm mượt) nếu không có Rhubarb hoặc Rhubarb lỗi.

Lưu ý Unicode: Rhubarb (boost) không chắc chắn đọc được path có dấu ("Làm việc"), nên file wav được
chép sang thư mục tạm ASCII trước khi gọi.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import uuid
import zipfile
from pathlib import Path

import numpy as np

from ..paths import RUNTIME
from . import audio_io

log = logging.getLogger(__name__)

RHUBARB_DIR = RUNTIME / "rhubarb"
RHUBARB_API = "https://api.github.com/repos/DanielSWolf/rhubarb-lip-sync/releases?per_page=10"
RHUBARB_FALLBACK_URL = ("https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/"
                        "Rhubarb-Lip-Sync-1.14.0-Windows.zip")
SHAPES = set("ABCDEFGHX")
FPS = 30

Viseme = tuple[float, str]

_download_failed = False  # chỉ thử tải 1 lần mỗi phiên


def find_rhubarb() -> Path | None:
    hits = sorted(RHUBARB_DIR.glob("**/rhubarb.exe")) if RHUBARB_DIR.exists() else []
    return hits[-1] if hits else None


def _latest_windows_zip_url() -> str:
    req = urllib.request.Request(RHUBARB_API, headers={"User-Agent": "storytoon",
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        releases = json.load(r)
    for rel in releases:
        tag = str(rel.get("tag_name", "")).lstrip("v")
        if rel.get("prerelease") or not tag.startswith("1."):
            continue
        for a in rel.get("assets", []):
            name = a.get("name", "").lower()
            if name.endswith(".zip") and ("windows" in name or "win32" in name):
                return a["browser_download_url"]
    return RHUBARB_FALLBACK_URL


def ensure_rhubarb() -> Path | None:
    """Trả về đường dẫn rhubarb.exe; tải bản Windows 1.x mới nhất về runtime/rhubarb nếu chưa có.
    Lỗi mạng -> None (visemes_for sẽ dùng fallback biên độ)."""
    global _download_failed
    exe = find_rhubarb()
    if exe or _download_failed:
        return exe
    try:
        try:
            url = _latest_windows_zip_url()
        except Exception as e:  # API GitHub bị giới hạn -> dùng URL cố định
            log.warning("Không đọc được danh sách bản phát hành Rhubarb (%s), dùng %s", e, RHUBARB_FALLBACK_URL)
            url = RHUBARB_FALLBACK_URL
        log.info("Đang tải Rhubarb Lip Sync: %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "storytoon"})
        with urllib.request.urlopen(req, timeout=120) as r:
            blob = r.read()
        RHUBARB_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            root = RHUBARB_DIR.resolve()
            for m in z.infolist():  # chống zip-slip
                if not (RHUBARB_DIR / m.filename).resolve().is_relative_to(root):
                    raise RuntimeError(f"Đường dẫn lạ trong zip: {m.filename}")
            z.extractall(RHUBARB_DIR)
    except Exception as e:
        _download_failed = True
        log.warning("Không tải được Rhubarb (%s) — dùng lip sync theo biên độ.", e)
        return None
    return find_rhubarb()


def _ascii_safe(p: Path) -> bool:
    try:
        str(p).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


_COPY_MARKER = ".storytoon-complete"
_copy_lock = threading.Lock()


def _rhubarb_runnable(exe: Path) -> Path:
    """Rhubarb tìm thư mục res/ cạnh exe; nếu path có dấu thì chép cả thư mục sang %LOCALAPPDATA%.

    Chép vào thư mục tạm rồi đổi tên (nguyên tử) + file đánh dấu: nhiều luồng/tiến trình cùng gọi lần đầu
    không đụng nhau (trước đây luồng khác thấy rhubarb.exe đã có trong khi res/ còn đang chép -> WinError 32),
    và bản chép dở (tắt máy giữa chừng) được chép lại."""
    if _ascii_safe(exe):
        return exe
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "storytoon" / exe.parent.name
    target = base / "rhubarb.exe"
    if not _ascii_safe(target):
        return exe
    marker = base / _COPY_MARKER
    with _copy_lock:
        if marker.is_file() and target.is_file():
            return target
        base.parent.mkdir(parents=True, exist_ok=True)
        tmp = base.with_name(f"{base.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            shutil.copytree(exe.parent, tmp)
            (tmp / _COPY_MARKER).write_text("ok", encoding="utf-8")
            if base.exists():  # bản cũ/chép dở: xoá (có thể thất bại nếu tiến trình khác đang chạy rhubarb)
                shutil.rmtree(base, ignore_errors=True)
            try:
                os.rename(tmp, base)
            except OSError:  # tiến trình khác vừa đổi tên xong, hoặc bản cũ không xoá được
                pass
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        if target.is_file():
            if not marker.is_file():
                log.warning("Bản Rhubarb trong %s có thể chưa đầy đủ (không thay được) — vẫn dùng.", base)
            return target
    return exe


def run_rhubarb(wav: Path, *, timeout: float = 300) -> list[Viseme]:
    exe = ensure_rhubarb()
    if exe is None:
        raise RuntimeError("Rhubarb không có sẵn")
    exe = _rhubarb_runnable(exe)
    with tempfile.TemporaryDirectory(prefix="stoon_lip_") as td:
        tmp_wav = Path(td) / "in.wav"
        shutil.copyfile(wav, tmp_wav)
        out_json = Path(td) / "out.json"
        cmd = [str(exe), "-q", "-f", "json", "-r", "phonetic", "--extendedShapes", "GHX",
               "-o", str(out_json), str(tmp_wav)]
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=str(exe.parent),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0 or not out_json.exists():
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(f"Rhubarb lỗi (mã {proc.returncode}): {err[-500:]}")
        data = json.loads(out_json.read_text(encoding="utf-8"))
    cues = [(round(float(c["start"]), 3), str(c["value"])) for c in data.get("mouthCues", [])]
    return [(t, s if s in SHAPES else "X") for t, s in cues]


def amplitude_visemes(wav: Path, *, fps: int = FPS) -> list[Viseme]:
    """Fallback: RMS mỗi khung 1/fps -> mức mở miệng, kèm độ sáng phổ để chọn E (tròn) / B (răng)."""
    data, sr = audio_io.read_wav(wav)
    mono = data.mean(axis=1)
    hop = max(1, sr // fps)
    n = len(mono) // hop
    if n == 0:
        return [(0.0, "X")]
    frames = mono[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    ref = float(np.percentile(rms, 95)) or 1e-6
    level = np.clip(rms / ref, 0, 1.2)
    # làm mượt: mở nhanh, khép chậm hơn
    smooth = np.empty_like(level)
    acc = 0.0
    for i, v in enumerate(level):
        acc = acc + (0.7 if v > acc else 0.35) * (v - acc)
        smooth[i] = acc
    # "độ sáng" phổ: tỉ lệ năng lượng thay đổi nhanh (xấp xỉ zero-crossing rate)
    zcr = (np.abs(np.diff(np.signbit(frames).astype(np.int8), axis=1)).sum(axis=1)) / hop

    shapes: list[str] = []
    for lv, z in zip(smooth, zcr):
        if lv < 0.08:
            s = "X"
        elif lv < 0.22:
            s = "A" if z < 0.05 else "B"
        elif lv < 0.45:
            s = "B" if z > 0.12 else "C"
        elif lv < 0.75:
            s = "E" if z < 0.03 else "C"
        else:
            s = "D"
        shapes.append(s)
    # giữ mỗi hình tối thiểu 2 khung để miệng không rung
    for i in range(1, len(shapes) - 1):
        if shapes[i] != shapes[i - 1] and shapes[i + 1] == shapes[i - 1]:
            shapes[i] = shapes[i - 1]
    out: list[Viseme] = []
    for i, s in enumerate(shapes):
        if not out or out[-1][1] != s:
            out.append((round(i / fps, 3), s))
    if out[-1][1] != "X":
        out.append((round(n / fps, 3), "X"))
    return out


def visemes_for(wav: Path, text: str = "", *, use_rhubarb: bool = True) -> list[Viseme]:
    """Viseme cho 1 file wav: [(giây từ đầu file, "A".."H"/"X"), ...], đã sắp theo thời gian.

    `text` hiện không truyền cho Rhubarb (xem docstring module) — giữ trong chữ ký để sau này
    engine khác (vd aligner tiếng Việt) dùng. Tự ưu tiên bản .16k.wav nếu có.
    """
    wav = Path(wav)
    src16 = wav.with_name(wav.stem + ".16k.wav")
    src = src16 if src16.exists() else wav
    if use_rhubarb:
        try:
            cues = run_rhubarb(src)
            if cues:
                return cues
        except Exception as e:
            log.warning("Rhubarb thất bại cho %s (%s) — dùng biên độ.", wav.name, e)
    return amplitude_visemes(wav)
