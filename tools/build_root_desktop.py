"""Build the folder-portable desktop app beside the canonical assets and projects.

Requires the runtime and WebView2 DLLs installed in the root; no dist dependency.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CSC = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
EXECUTABLE = ROOT / 'StoryToon-Desktop-Portable.exe'


def compile_exe(source: str, output: Path, references: list[Path | str]) -> None:
    args = [str(CSC), '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/utf8output',
            '/out:' + str(output), '/reference:System.dll', '/reference:System.Core.dll',
            '/reference:System.Drawing.dll', '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll']
    args += ['/reference:' + str(ref) for ref in references]
    subprocess.run([*args, str(ROOT / 'desktop' / source)], check=True)


def main() -> int:
    for name in ('runtime/python/python.exe', 'runtime/ffmpeg/ffmpeg.exe',
                 'runtime/node/node.exe', 'storytoon/vendor/capcut_tts/bridge.js',
                 'storytoon/vendor/capcut_tts/capcut_tts.js',
                 'storytoon/vendor/capcut_tts/voices/vi.json',
                 'storytoon/vendor/capcut_tts/voices/th.json',
                 'storytoon/vendor/capcut_tts/voices/ko.json',
                 'Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll',
                 'WebView2Loader.dll', 'storytoon/desktop_server.py'):
        if not (ROOT / name).is_file():
            raise RuntimeError('Missing root app dependency: ' + name)
    temporary = EXECUTABLE.with_suffix('.new.exe')
    compile_exe('StoryToon.cs', temporary,
                [ROOT/'Microsoft.Web.WebView2.Core.dll', ROOT/'Microsoft.Web.WebView2.WinForms.dll'])
    temporary.replace(EXECUTABLE)
    EXECUTABLE.with_suffix('.exe.config').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.7.2"/>'
        '</startup><appSettings><add key="EnableWindowsFormsHighDpiAutoResizing" value="true"/>'
        '</appSettings></configuration>\n', encoding='utf-8')
    print('Built root desktop app: ' + str(EXECUTABLE), flush=True)
    print('Data root: ' + str(ROOT) + ' (no dist dependency)', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
