from pathlib import Path
import sys,json
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from storytoon.asset_library import catalog
data=catalog()
for kind in data:
    items=data[kind]
    w,h=240,220
    sheet=Image.new('RGB',(w*5,h*((len(items)+4)//5)),'#e8e8e8')
    d=ImageDraw.Draw(sheet)
    for i,e in enumerate(items):
        im=Image.open(e['preview']).convert('RGBA')
        im.thumbnail((w-12,h-35))
        x,y=(i%5)*w,(i//5)*h
        sheet.paste(im,(x+(w-im.width)//2,y),im)
        d.text((x+5,y+h-30),e['id'],fill='black')
    sheet.save(ROOT/f'runtime/video-review/{kind}-final.jpg')
    print(kind,len(items),sum(e['ready'] for e in items))
p=ROOT/'dist/StoryToon-data/projects/demo/storyboard.json'
sb=json.loads(p.read_text(encoding='utf-8'))
print('Installed demo:',len(sb['shots']),'shots; props:',[(s['id'],c.get('prop')) for s in sb['shots'] for c in s.get('characters',[]) if c.get('prop')])
