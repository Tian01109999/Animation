"""Package the root portable app without local accounts or generated work."""
from pathlib import Path
import hashlib
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storytoon import __version__

ROOT_FILES = (
    'StoryToon-Desktop-Portable.exe', 'StoryToon-Desktop-Portable.exe.config',
    'StoryToon.bat', 'Microsoft.Web.WebView2.Core.dll',
    'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll',
    'WebView2-LICENSE.txt', 'README.md',
)
TREES = ('storytoon', 'assets', 'runtime/python', 'runtime/node',
         'runtime/codex', 'runtime/ffmpeg', 'runtime/rhubarb')


def main():
    output = ROOT / 'dist' / f'StoryToon-{__version__}-Windows-x64.zip'
    output.parent.mkdir(exist_ok=True)
    files = [(ROOT / name, name) for name in ROOT_FILES]
    files.append((ROOT / 'config.example.yaml', 'config.yaml'))
    for directory in TREES:
        source = ROOT / directory
        if not source.is_dir():
            raise RuntimeError(f'Missing dependency: {directory}')
        for path in sorted(source.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo'):
                continue
            if (path.name.lower() in ('auth.json', 'credentials.json', '.env')
                    or path.suffix == '.dat' and 'session' in path.name.lower()):
                raise RuntimeError(f'Account data found in package input: {relative}')
            files.append((path, relative.as_posix()))
    temporary = output.with_suffix('.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in files:
            archive.write(path, 'StoryToon/' + name)
    with zipfile.ZipFile(temporary) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f'Corrupt archive entry: {bad}')
    temporary.replace(output)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print(f'Created {output.name}: {len(files)} files, {output.stat().st_size:,} bytes')
    print(f'SHA256 {digest}')


if __name__ == '__main__':
    main()
