from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw
from storytoon.asset_library import catalog,validate
from storytoon.schema import Storyboard,CharacterDef,LocationDef,Shot,CharacterInShot
from storytoon.render.compositor import ShotRenderer,render_shot
from storytoon.render.skutil import save_png

out=ROOT/'runtime/library-render-smoke'
out.mkdir(exist_ok=True)
sheet=Image.new('RGB',(1280,3*210),'#eeeeee')
d=ImageDraw.Draw(sheet)
for i,entry in enumerate(catalog()['characters']):
    style=entry['style']
    bg='dong_co_hoat_hinh' if style=='stick' else 'phong_lam_viec'
    shot=Shot(id=f'check{i}',location='room',framing='medium',camera='push_in_slow',duration=2,
              characters=[CharacterInShot(id='story_role',action='talk')])
    sb=Storyboard(title='Test existing assets',style=style,
        characters=[CharacterDef(id='story_role',name='Nhân vật câu chuyện',gender=entry['gender'],age=entry['age'],asset_id=entry['id'])],
        locations=[LocationDef(id='room',name='Phòng',asset_id=bg)],shots=[shot])
    validate(sb)
    renderer=ShotRenderer(shot,sb,None,width=640,height=360,fps=24,watermark='')
    file=out/f"{entry['id']}.png"
    save_png(renderer.frame(24),file)
    im=Image.open(file).convert('RGB').resize((320,180))
    x,y=(i%4)*320,(i//4)*210
    sheet.paste(im,(x,y));d.text((x+3,y+183),entry['id'],fill='black')
    if entry['id'] in ('nu_tre_ao_xanh','nguoi_que_tre_vuong_mien'):
        render_shot(shot,sb,out,out/f"{entry['id']}.mp4",width=640,height=360,fps=24,n_frames=48)
sheet.save(out/'frames.jpg')
print('PASS: all ten library characters rendered, two MP4 clips encoded.',flush=True)
