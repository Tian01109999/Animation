"""Small upgrade ZIP for an existing root-portable installation (0.2.0+)."""
from pathlib import Path
import hashlib
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storytoon import __version__


def main():
    output = ROOT / 'dist' / f'StoryToon-App-Patch-{__version__}.zip'
    output.parent.mkdir(exist_ok=True)
    files = [ROOT / name for name in ('StoryToon-Desktop-Portable.exe',
             'StoryToon-Desktop-Portable.exe.config', 'README.md')]
    files += [p for p in sorted((ROOT / 'storytoon').rglob('*'))
              if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')]
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source in files:
            archive.write(source, source.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise ValueError('Corrupt app patch ZIP')
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print(f'{output.name}: {output.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
