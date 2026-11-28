"""Build the full in-app update package: StoryToon-Update-<version>.zip (+ .sha256).

Contains the desktop EXE, storytoon/ code and the whole assets/ library, plus update.json
with the changelog and the files removed since earlier published packages.
Usage: python tools/prepare_update.py --notes docs/release_notes/1.1.0.md
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storytoon import __version__
from storytoon.updater import ASSETS_VERSION_FILE, EXE_NAME

ASSETS_LIBRARY_VERSION = '1.2.0'   # marker so old assets-only clients stop prompting


def previous_paths(dist: Path) -> set[str]:
    """Root-relative paths shipped by earlier packages found in dist/."""
    seen: set[str] = set()
    for z in dist.glob('*.zip'):
        if z.name.startswith('StoryToon-Update-'):
            continue
        try:
            with zipfile.ZipFile(z) as archive:
                for name in archive.namelist():
                    if name.endswith('/'):
                        continue
                    if name.startswith('StoryToon/'):
                        name = name[len('StoryToon/'):]
                    if name.startswith(('storytoon/', 'assets/')):
                        seen.add(name)
        except zipfile.BadZipFile:
            continue
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notes', required=True, help='Markdown/text file with the changelog')
    parser.add_argument('--exe', help='Desktop EXE to ship (default: .new.exe build, else the root EXE)')
    args = parser.parse_args()
    notes = Path(args.notes).read_text(encoding='utf-8').strip()
    version = __version__
    if args.exe:
        exe = Path(args.exe)
    else:
        exe = ROOT / 'StoryToon-Desktop-Portable.new.exe'
        if not exe.exists():
            exe = ROOT / EXE_NAME
    files: list[tuple[Path, str]] = [(exe, EXE_NAME), (ROOT / 'README.md', 'README.md')]
    config = ROOT / (EXE_NAME + '.config')
    if config.exists():
        files.append((config, EXE_NAME + '.config'))
    marker = 'assets/' + ASSETS_VERSION_FILE
    for tree in ('storytoon', 'assets'):
        for path in sorted((ROOT / tree).rglob('*')):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if '__pycache__' in rel or path.suffix in ('.pyc', '.pyo', '.updating') or rel == marker:
                continue
            if path.name.lower() in ('auth.json', 'credentials.json', '.env'):
                raise RuntimeError(f'Account data in package input: {rel}')
            files.append((path, rel))
    current = {rel for _, rel in files}
    deleted = sorted(p for p in previous_paths(ROOT / 'dist') if p not in current and p != marker)
    manifest = {'version': version, 'notes': notes, 'delete': deleted}
    output = ROOT / 'dist' / f'StoryToon-Update-{version}.zip'
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix('.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, rel in files:
            archive.write(path, rel)
        archive.writestr(marker, json.dumps({'schema': 1, 'version': ASSETS_LIBRARY_VERSION}, indent=2) + '\n')
        archive.writestr('update.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    with zipfile.ZipFile(temporary) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f'Corrupt archive entry: {bad}')
    temporary.replace(output)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print(f'{output.name}: {len(files)} files, {len(deleted)} deletions, {output.stat().st_size:,} bytes')
    print(f'SHA256 {digest}')
    for rel in deleted[:40]:
        print('  delete', rel)


if __name__ == '__main__':
    main()
