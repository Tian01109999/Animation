"""Sample an attached reference video for visual asset review (no image generation)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--count', type=int, default=40)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    times = [round(5 + i * (args.duration - 10) / (args.count - 1), 2) for i in range(args.count)]
    def sample(t):
        dest = args.out / f'{t:08.2f}.jpg'
        if not dest.exists():
            subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', str(t), '-i',
                            str(args.video), '-frames:v', '1', '-vf', 'scale=640:-1', '-q:v', '2',
                            '-y', str(dest)], check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return dest
    with ThreadPoolExecutor(max_workers=3) as pool:
        files = list(pool.map(sample, times))
    for start in range(0, len(files), 20):
        sheet = Image.new('RGB', (1600, 4 * 204), '#242424')
        draw = ImageDraw.Draw(sheet)
        for i, file in enumerate(files[start:start+20]):
            x, y = (i % 5) * 320, (i // 5) * 204
            with Image.open(file) as frame:
                sheet.paste(frame.resize((320, 180)), (x, y))
            draw.text((x+5, y+182), file.stem+' sec', fill='white')
        sheet.save(args.out / f'contact-{start//20+1}.jpg', quality=93)
    print(f'Reviewed {len(files)} sample frames: {args.out}', flush=True)


if __name__ == '__main__':
    main()
