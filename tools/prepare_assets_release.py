"""Build an assets-only ZIP. Run with --version X.Y.Z after editing assets."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storytoon.updater import ASSETS_VERSION_FILE, version_tuple


def build(version: str, root: Path = ROOT) -> Path:
    version_tuple(version)
    if version.startswith('v'):
        raise ValueError('Use X.Y.Z without a v prefix')
    assets = root / 'assets'
    marker = assets / ASSETS_VERSION_FILE
    if marker.exists():
        previous = json.loads(marker.read_text(encoding='utf-8'))['version']
        if version_tuple(version) < version_tuple(previous):
            raise ValueError('Assets version must not decrease')
    files = []
    for source in sorted(assets.rglob('*')):
        if source.is_symlink():
            raise ValueError(f'Symlink in assets: {source}')
        if source.is_file() and source != marker:
            if not source.resolve().is_relative_to(assets.resolve()):
                raise ValueError('Asset path outside assets directory')
            files.append(source)
    if not files:
        raise ValueError('Assets directory is empty')
    metadata = json.dumps({'schema': 1, 'version': version}, ensure_ascii=False, indent=2) + '\n'
    output = root / 'dist' / f'StoryToon-Assets-{version}.zip'
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix('.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source in files:
            archive.write(source, source.relative_to(root).as_posix())
        archive.writestr('assets/' + ASSETS_VERSION_FILE, metadata)
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip():
            raise ValueError('Corrupt assets ZIP')
    temporary.replace(output)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    marker.write_text(metadata, encoding='utf-8')
    print(f'{output.name}: {len(files)} asset files, {output.stat().st_size:,} bytes', flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    build(parser.parse_args().version)
