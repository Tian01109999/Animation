"""Đóng gói StoryToon portable cho Windows 10/11 x64 (không cần cài Python, không cần ffmpeg trong PATH).

Chạy bằng Python của venv phát triển:
    runtime\\venv\\Scripts\\python.exe tools\\build_portable.py [--zip] [--build-date YYYY-MM-DD]

Kết quả:  dist\\StoryToon\\              (xoá và dựng lại mỗi lần chạy; dist\\_cache được giữ)
          dist\\StoryToon-<ver>-win64.zip (khi có --zip)

Cấu trúc bản portable:
    StoryToon.bat, StoryToon-CLI.bat, "StoryToon (an cua so).vbs", "Huong dan nhanh.txt", VERSION.txt
    config.yaml (sạch: không key, không project URL, chrome_path tự dò)
    storytoon\\  assets\\ (trừ assets\\library)  docs\\  tools\\make_placeholder_assets.py  README.md
    projects\\demo\\script.txt + storyboard.json
    runtime\\python\\   CPython embeddable (cùng bản 3.13.x với venv) + Lib\\site-packages của venv
    runtime\\ffmpeg\\   ffmpeg.exe, ffprobe.exe (lấy từ runtime\\ffmpeg hoặc PATH của máy build)
    runtime\\rhubarb\\  Rhubarb Lip Sync
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = DIST / "StoryToon"
CACHE = DIST / "_cache"
VENV_SITE = ROOT / "runtime" / "venv" / "Lib" / "site-packages"

PY_FTP = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
UA = {"User-Agent": "storytoon-portable-build"}

# Gói chỉ dùng khi phát triển / cài đặt — không đưa vào bản portable (tên thư mục/top-level module).
DEV_ONLY = {"pip", "setuptools", "wheel", "_distutils_hack", "pkg_resources",
            "pyflakes", "pytest", "_pytest", "pluggy", "iniconfig", "py", "cv2", "opencv_python_headless"}
# Thư mục test lớn chắc chắn không được import khi chạy.
SAFE_TEST_DIRS = {("numpy",), ("pandas",)}
ASSET_DIRS = ["characters", "actions", "locations", "inserts", "fonts", "music", "sfx"]


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------------------- helpers
def _on_rm_error(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(p: Path) -> None:
    if p.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(p, onexc=_on_rm_error)
        else:  # pragma: no cover
            shutil.rmtree(p, onerror=_on_rm_error)


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for m in zf.infolist():
        if not (dest / m.filename).resolve().is_relative_to(root):
            raise RuntimeError(f"Mục zip không an toàn: {m.filename}")
    zf.extractall(dest)


def write_text(p: Path, text: str, *, bom: bool = False, crlf: bool = True) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8-sig" if bom else "utf-8"))


# ------------------------------------------------------------------------------- python embed
def _download(url: str, dest: Path) -> bool:
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        if e.code == 404:
            return False
        raise
    try:
        with zipfile.ZipFile(tmp) as z:
            if z.testzip() is not None or "python.exe" not in z.namelist():
                raise RuntimeError("zip hỏng")
    except (zipfile.BadZipFile, RuntimeError):
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dest)
    return True


def get_embed_zip(version: str) -> tuple[Path, str]:
    """Tải (hoặc lấy từ cache) python-<ver>-embed-amd64.zip; không có thì lấy bản 3.13.x gần nhất."""
    CACHE.mkdir(parents=True, exist_ok=True)
    major, minor, patch = (int(x) for x in version.split(".")[:3])
    cands = [patch] + [p for d in range(1, 40) for p in (patch - d, patch + d) if 0 <= p <= patch + 5]
    for p in cands:
        v = f"{major}.{minor}.{p}"
        dest = CACHE / f"python-{v}-embed-amd64.zip"
        if dest.exists():
            log(f"  dùng cache {dest.name}")
            return dest, v
    for p in cands:
        v = f"{major}.{minor}.{p}"
        dest = CACHE / f"python-{v}-embed-amd64.zip"
        url = PY_FTP.format(v=v)
        log(f"  tải {url}")
        try:
            if _download(url, dest):
                return dest, v
        except (urllib.error.URLError, OSError) as e:
            log(f"  lỗi tải {v}: {e}")
    raise RuntimeError(f"Không tải được CPython embeddable {major}.{minor}.x cho Windows amd64")


def build_python(rt: Path, version: str) -> str:
    log(f"[python] CPython embeddable (venv: {version})")
    zpath, got = get_embed_zip(version)
    if got != version:
        log(f"  CẢNH BÁO: không có bản {version}, dùng {got} (cùng ABI cp{version.split('.')[0]}{version.split('.')[1]})")
    pydir = rt / "python"
    pydir.mkdir(parents=True)
    with zipfile.ZipFile(zpath) as z:
        safe_extract(z, pydir)
    tag = "python{}{}".format(*version.split(".")[:2])
    pth = pydir / f"{tag}._pth"
    pth.write_text(
        f"{tag}.zip\n.\nLib\\site-packages\n..\\..\n\n# import site: process .pth files in Lib\\site-packages\nimport site\n",
        encoding="utf-8")
    return got


def _ignore_site(src_root: Path):
    def ignore(dirpath: str, names: list[str]) -> set[str]:
        d = Path(dirpath)
        rel = d.relative_to(src_root).parts
        out = set()
        for n in names:
            low = n.lower()
            if n == "__pycache__" or low.endswith((".pyc", ".pyo")):
                out.add(n)
            elif not rel:  # cấp site-packages
                top = n.split("-")[0].split(".")[0].lower() if low.endswith((".dist-info", ".egg-info")) \
                    else (n[:-3] if low.endswith(".py") else n).lower()
                if top in DEV_ONLY or top == 'google_genai' or low == "distutils-precedence.pth":
                    out.add(n)
            elif rel == ('google',) and n == 'genai':
                out.add(n)
            elif n == "tests" and rel[:1] and (rel[0],) in SAFE_TEST_DIRS and (d / n).is_dir():
                out.add(n)
        return out
    return ignore


def copy_site_packages(rt: Path) -> None:
    log("[python] chép site-packages từ venv")
    dst = rt / "python" / "Lib" / "site-packages"
    shutil.copytree(VENV_SITE, dst, ignore=_ignore_site(VENV_SITE))
    # Playwright: chỉ cần driver (node) — trình duyệt là Chrome/Edge của người dùng qua CDP.
    pw = dst / "playwright" / "driver"
    node = pw / "node.exe"
    if not node.exists():
        raise RuntimeError(f"Thiếu driver Playwright: {node}")
    local_browsers = pw / "package" / ".local-browsers"
    if local_browsers.exists():
        rmtree(local_browsers)
    # pywin32 (nếu có): DLL pythoncomXY/pywintypesXY phải nằm cạnh python.exe.
    sys32 = dst / "pywin32_system32"
    if sys32.is_dir():
        for dll in sys32.glob("*.dll"):
            shutil.copy2(dll, rt / "python" / dll.name)
        log("  pywin32: đã chép DLL cạnh python.exe")


# --------------------------------------------------------------------------------- ffmpeg/rhubarb
def find_exe(name: str) -> Path:
    for cand in (ROOT / "runtime" / "ffmpeg" / f"{name}.exe", ROOT / "runtime" / "ffmpeg" / "bin" / f"{name}.exe"):
        if cand.is_file():
            return cand
    w = shutil.which(name)
    if not w:
        raise RuntimeError(f"Không tìm thấy {name}.exe (runtime\\ffmpeg hoặc PATH của máy build)")
    return Path(w)


def copy_ffmpeg(rt: Path) -> None:
    log("[ffmpeg] chép ffmpeg.exe, ffprobe.exe")
    d = rt / "ffmpeg"
    d.mkdir(parents=True)
    src = None
    for name in ("ffmpeg", "ffprobe"):
        src = find_exe(name)
        shutil.copy2(src, d / f"{name}.exe")
        log(f"  {src}")
    # Giấy phép (GPL) của bản build ffmpeg nếu có.
    for lic in (src.parent / "LICENSE", src.parent.parent / "LICENSE", src.parent.parent / "LICENSE.txt"):
        if lic.is_file():
            shutil.copy2(lic, d / "LICENSE.txt")
            break


def copy_rhubarb(rt: Path) -> None:
    src = ROOT / "runtime" / "rhubarb"
    if not any(src.glob("**/rhubarb.exe")):
        log("[rhubarb] CẢNH BÁO: không có runtime\\rhubarb — app sẽ tự tải khi cần (cần mạng)")
        return
    log("[rhubarb] chép runtime\\rhubarb")
    shutil.copytree(src, rt / "rhubarb", ignore=shutil.ignore_patterns("__pycache__"))


def copy_codex(rt: Path) -> None:
    source = ROOT / 'runtime' / 'codex'
    candidates = list(source.glob('node_modules/@openai/codex-*/vendor/*/bin/codex.exe'))
    executable = source / 'codex.exe'
    if not executable.exists() and candidates:
        executable = candidates[0]
    if not executable.exists():
        raise RuntimeError('Thiếu Codex CLI: npm install --prefix runtime/codex @openai/codex')
    destination = rt / 'codex'
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, destination / 'codex.exe')
    if (source / 'LICENSE.txt').exists():
        shutil.copy2(source / 'LICENSE.txt', destination / 'LICENSE.txt')
    helper = executable.with_name('codex-code-mode-host.exe')
    if helper.exists():
        shutil.copy2(helper, destination / helper.name)


# ---------------------------------------------------------------------------------------- app
def copy_app() -> None:
    log("[app] chép mã nguồn, tài sản, tài liệu, project demo")
    pyc = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(ROOT / "storytoon", OUT / "storytoon", ignore=pyc)
    for name in ASSET_DIRS:  # assets\library là dữ liệu người dùng -> không chép
        src = ROOT / "assets" / name
        if src.is_dir():
            shutil.copytree(src, OUT / "assets" / name, ignore=pyc)
    for f in (ROOT / "assets").iterdir():
        if f.is_file():
            shutil.copy2(f, OUT / "assets" / f.name)
    (OUT / "tools").mkdir()
    shutil.copytree(ROOT / "docs", OUT / "docs", ignore=pyc)
    shutil.copy2(ROOT / "README.md", OUT / "README.md")
    demo = OUT / "projects" / "demo"
    demo.mkdir(parents=True)
    for n in ("script.txt", "storyboard.json"):
        s = ROOT / "projects" / "demo" / n
        if s.is_file():
            shutil.copy2(s, demo / n)


def write_clean_config() -> None:
    import yaml

    src = ROOT / "config.yaml"
    data = (yaml.safe_load(src.read_text(encoding="utf-8")) if src.exists() else None) or {}
    data.pop('gemini',None)
    data.setdefault('script', {})['provider'] = 'chatgpt'
    data["image_provider"] = "library"
    data.pop('flow',None)
    data.setdefault('library',{})['style']='cutout'
    header = "# Cấu hình StoryToon Desktop\n"
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=None)
    (OUT / "config.yaml").write_text(header + body, encoding="utf-8")


# ----------------------------------------------------------------------------------- launchers
BAT_UI = r"""@echo off
rem StoryToon (portable) - mo giao dien tren http://127.0.0.1:7860
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY=%~dp0runtime\python\python.exe"
if not exist "%PY%" (
  echo Khong tim thay runtime\python\python.exe - hay chep lai ca thu muc StoryToon.
  if not "%STORYTOON_NO_PAUSE%"=="1" pause
  exit /b 1
)
set "PYTHONHOME="
set "PYTHONPATH="
set PYTHONUTF8=1
set "PATH=%~dp0runtime\ffmpeg;%~dp0runtime\python;%PATH%"
rem runtime\python\python313._pth bat che do isolated (bo qua bien PYTHON*) nen bat UTF-8 bang -X utf8
"%PY%" -X utf8 -m storytoon.ui %*
if errorlevel 1 if not "%STORYTOON_NO_PAUSE%"=="1" pause
endlocal
"""

BAT_CLI = r"""@echo off
rem StoryToon (portable) - cua so dong lenh voi Python portable tren PATH
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set PYTHONUTF8=1
set "PATH=%~dp0runtime\python;%~dp0runtime\ffmpeg;%PATH%"
title StoryToon CLI
echo ================================================================
echo  StoryToon CLI  (python = runtime\python\python.exe)
echo ================================================================
echo  storytoon --help                       xem tat ca lenh
echo  storytoon new "Ten phim"               tao projects\^<slug^>\script.txt
echo  storytoon breakdown ^<project^>          kich ban -^> storyboard (ChatGPT)
echo  storytoon run ^<project^>                chay tat ca cac buoc
echo  storytoon run demo --steps assets,audio,render --provider library
echo  storytoon ui                           mo giao dien
echo.
echo  ("storytoon" = python -X utf8 -m storytoon.cli)
echo.
cmd /k "doskey storytoon=python -X utf8 -m storytoon.cli $*"
"""

VBS = r"""' StoryToon (portable) - mo giao dien, khong hien cua so dong lenh.
' De tat app: dong tab trinh duyet roi ket thuc "python.exe" trong Task Manager,
' hoac dung StoryToon.bat (co cua so, dong cua so la tat).
Option Explicit
Dim sh, fso, root
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root
sh.Environment("Process")("STORYTOON_NO_PAUSE") = "1"
sh.Run Chr(34) & root & "\StoryToon.bat" & Chr(34), 0, False
"""

GUIDE = (ROOT / "README.md").read_text(encoding="utf-8")



def write_launchers(version: str, build_date: str, py_version: str) -> None:
    log("[launchers] StoryToon.bat, StoryToon-CLI.bat, vbs, hướng dẫn, VERSION.txt")
    write_text(OUT / "StoryToon.bat", BAT_UI)
    write_text(OUT / "StoryToon-CLI.bat", BAT_CLI)
    write_text(OUT / "StoryToon (an cua so).vbs", VBS)
    write_text(OUT / "Huong dan nhanh.txt", GUIDE.format(version=version), bom=True)
    write_text(OUT / "VERSION.txt",
               f"StoryToon {version}\nBuild date: {build_date}\nPython: {py_version} (embeddable, win64)\n")


# ---------------------------------------------------------------------------------- precompile
def precompile(pyexe: Path) -> None:
    """Biên dịch sẵn .pyc (đường dẫn tương đối theo gốc app) để lần chạy đầu nhanh hơn."""
    # checked-hash: .pyc vẫn hợp lệ sau khi giải nén zip (zip làm tròn mtime); đường dẫn trong .pyc
    # là tương đối, và importlib tự sửa co_filename theo vị trí thật khi nạp.
    log("[compile] biên dịch .pyc (checked-hash)")
    targets = ["storytoon", r"runtime\python\Lib\site-packages"]
    cmd = [str(pyexe), "-X", "utf8", "-m", "compileall", "-q", "-j", "0",
           "--invalidation-mode", "checked-hash", *targets]
    r = subprocess.run(cmd, cwd=str(OUT), env=clean_env(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:  # vài file test/py2 trong gói bên thứ ba có thể lỗi cú pháp — không chặn build
        log(f"  compileall báo lỗi (bỏ qua): {(r.stdout + r.stderr).strip()[-600:]}")


# --------------------------------------------------------------------------------------- verify
def clean_env() -> dict[str, str]:
    keep = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
            "COMSPEC", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "HOMEDRIVE", "HOMEPATH",
            "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMPUTERNAME", "USERNAME")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PATH"] = r"C:\Windows\System32;C:\Windows"
    env["PYTHONUTF8"] = "1"
    return env


VERIFY_CODE = r"""
import sys, os
import storytoon, gradio, skia, av, glfw, playwright, google.genai, edge_tts
from storytoon import tools_bin
ff = tools_bin.ffmpeg_exe(); fp = tools_bin.ffprobe_exe()
root = os.path.normcase(os.path.dirname(os.path.dirname(storytoon.__file__)))
assert os.path.normcase(ff).startswith(root), ff
assert os.path.normcase(fp).startswith(root), fp
assert os.path.normcase(sys.executable).startswith(root), sys.executable
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
with ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as ex:
    res = list(ex.map(abs, [-1, -2]))
assert res == [1, 2], res
print("python", sys.version.split()[0], "| exe", sys.executable)
print("ffmpeg", ff)
print("ok")
"""


def verify(pyexe: Path) -> bool:
    log("[verify] kiểm tra trong môi trường sạch (PATH chỉ có System32)")
    ok = True
    r = subprocess.run([str(pyexe), "-X", "utf8", "-c", VERIFY_CODE], cwd=str(OUT), env=clean_env(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    log((r.stdout + r.stderr).strip())
    ok &= r.returncode == 0
    r = subprocess.run([str(pyexe), "-m", "playwright", "--version"], cwd=str(OUT), env=clean_env(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    log(f"  playwright driver: {(r.stdout + r.stderr).strip()}")
    ok &= r.returncode == 0
    r = subprocess.run([str(OUT / "runtime" / "ffmpeg" / "ffmpeg.exe"), "-hide_banner", "-version"],
                       env=clean_env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(f"  {r.stdout.splitlines()[0] if r.stdout else r.stderr.strip()}")
    ok &= r.returncode == 0
    return ok


# ------------------------------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    global OUT
    ap = argparse.ArgumentParser(description="Đóng gói StoryToon portable -> dist\\StoryToon")
    ap.add_argument("--zip", action="store_true", help="tạo thêm dist\\StoryToon-<ver>-win64.zip")
    ap.add_argument("--build-date", default=_dt.date.today().isoformat())
    ap.add_argument("--no-compile", action="store_true", help="không biên dịch sẵn .pyc")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--output-name", choices=["StoryToon", "StoryToon-Desktop"], default="StoryToon")
    a = ap.parse_args(argv)
    OUT = DIST / a.output_name

    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        log("Chỉ build được trên Windows x64.")
        return 2
    if not VENV_SITE.is_dir():
        log(f"Không thấy venv: {VENV_SITE}")
        return 2
    py_version = platform.python_version()
    if not py_version.startswith("3.13."):
        log(f"CẢNH BÁO: đang chạy Python {py_version}; venv được thiết kế cho 3.13")

    sys.path.insert(0, str(ROOT))
    from storytoon import __version__ as version

    # Chỉ xoá đúng dist\StoryToon (giữ dist\_cache và các zip cũ).
    assert OUT.resolve().parent == DIST.resolve() and OUT.name in {"StoryToon", "StoryToon-Desktop"}
    # A previously used portable folder may contain real user data. Never rebuild it.
    if any((OUT / p).exists() for p in (".env", "runtime/chrome-profile", "runtime/desktop-webview", "runtime/jobs.sqlite")):
        raise RuntimeError(f"Không ghi đè bản portable đã có dữ liệu người dùng: {OUT}")
    log(f"Đóng gói StoryToon {version} -> {OUT}")
    rmtree(OUT)
    OUT.mkdir(parents=True)
    rt = OUT / "runtime"

    got = build_python(rt, py_version)
    copy_site_packages(rt)
    copy_ffmpeg(rt)
    copy_rhubarb(rt)
    copy_codex(rt)
    copy_app()
    write_clean_config()
    write_launchers(version, a.build_date, got)

    pyexe = rt / "python" / "python.exe"
    if not a.no_compile:
        precompile(pyexe)

    # Chắc chắn không lọt dữ liệu cá nhân.
    for bad in (".env", "runtime/chrome-profile", "runtime/jobs.sqlite", "runtime/flow_usage.json",
                "logs", "assets/library", "runtime/venv"):
        if (OUT / bad).exists():
            raise RuntimeError(f"Bản đóng gói chứa dữ liệu không được phép: {bad}")
    stray = [p for p in (OUT / "projects").iterdir() if p.name != "demo"]
    if stray:
        raise RuntimeError(f"Bản đóng gói chứa project khác: {stray}")

    ok = True
    if not a.no_verify:
        ok = verify(pyexe)

    size = dir_size(OUT)
    log(f"\nThư mục: {OUT}\nDung lượng: {human(size)} ({size:,} byte)")

    if a.zip:
        zpath = DIST / f"StoryToon-{version}-win64.zip"
        zpath.unlink(missing_ok=True)
        log(f"[zip] {zpath.name} ...")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(OUT.rglob("*")):
                z.write(f, Path("StoryToon") / f.relative_to(OUT))
        log(f"  {zpath} ({human(zpath.stat().st_size)})")

    log("XONG" if ok else "XONG nhưng kiểm tra thất bại — xem log ở trên")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
