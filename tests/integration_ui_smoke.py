"""Khói UI: dựng app (gọi thử các hàm nạp dữ liệu), rồi khởi động server thật ở cổng riêng, GET /, tắt.

    runtime\\venv\\Scripts\\python.exe tests\\integration_ui_smoke.py
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PORT = 7891


def in_process() -> None:
    from storytoon import ui
    app = ui.build_app()
    assert app is not None
    rows = ui.shot_rows(ui._sb_or_none("demo"))
    assert rows and rows[0][0] == "s001", rows[:1]
    md = ui._assets_md("demo")
    assert "chu_tu" in md and "cho_dem" in md, md
    from storytoon.asset_library import gallery_items
    print("build_app OK —", len(rows), "shot,", len(gallery_items()), "nhân vật thư viện")


def server() -> None:
    py = ROOT / "runtime" / "venv" / "Scripts" / "python.exe"
    proc = subprocess.Popen([str(py), "-m", "storytoon.ui", "--port", str(PORT), "--no-browser"], cwd=str(ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=3) as r:
                    body = r.read().decode("utf-8", "ignore")
                    assert r.status == 200 and "StoryToon" in body, r.status
                    print(f"GET / -> {r.status}, {len(body)} byte, có 'StoryToon'")
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/config", timeout=5) as c:
                        cfg = c.read().decode("utf-8", "ignore")
                    assert "Tài khoản & Cài đặt" in cfg and "Xuất phim" in cfg
                    print("GET /config -> có đủ tab")
                    return
            except OSError:
                time.sleep(1)
            if proc.poll() is not None:
                break
        out = proc.stdout.read().decode("utf-8", "ignore") if proc.stdout else ""
        raise SystemExit(f"UI không khởi động được:\n{out[-3000:]}")
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    in_process()
    server()
    print("OK")
