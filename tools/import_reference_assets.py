"""Build reusable assets by cropping supplied video pixels. No generative model is used.

Curated recipes are reviewed against contact sheets. Provenance and coverage are kept
with every asset; a portrait is never claimed to contain an unseen full body.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / 'dist/StoryToon-data/runtime/ffmpeg/ffmpeg.exe'
DOWNLOADS = Path.home() / 'Downloads'
BUNS = DOWNLOADS / 'อย่ากินซาลาเปาไส้พิเศษ! ｜ ลุงข้างบ้านเอาเนื้ออะไรมาทำ (เต็มเรื่อง).mp4'
ANTS = next((DOWNLOADS / 'Điều Gì Xảy Ra Khi Đi Tiểu Vào Tổ Kiến Lửa Trong 1 Tuần Liên Tục？_parts').glob('*.mp4'))
CACHE = ROOT / 'runtime/video-review/extraction'


def frame(source: Path, second: float) -> Image.Image:
    key = hashlib.sha256((source.name + str(second)).encode()).hexdigest()[:16]
    dest = CACHE / f'{key}.png'
    CACHE.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-ss', str(second),
                        '-i', str(source), '-frames:v', '1', '-y', str(dest)], check=True)
    return Image.open(dest).convert('RGB')


def save_meta(folder, name, data):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def provenance(source, second, crop):
    return {'kind': 'video_extract', 'source': source.name, 'timestamp_s': second, 'crop': crop,
            'generated': False, 'reviewed': True}


def plate(identifier, label, second, crop, tags, *, source=BUNS, kind='locations', tod='indoor', style='cutout'):
    image = frame(source, second).crop(crop)
    # Uniform location dimensions; this is resampling existing pixels, not filling unseen regions.
    width, height = image.size
    ratio = 16/9
    if width/height > ratio:
        target = round(height*ratio)
        image = image.crop(((width-target)//2, 0, (width+target)//2, height))
    else:
        target = round(width/ratio)
        image = image.crop((0, (height-target)//2, width, (height+target)//2))
    image = image.resize((1920,1080), Image.Resampling.LANCZOS)
    if kind == 'inserts':
        folder = ROOT / 'assets/inserts'
        folder.mkdir(parents=True, exist_ok=True)
        image.save(folder / f'{identifier}.jpg', quality=94)
        save_meta(folder, f'{identifier}.json', {'id':identifier,'label':label,'tags':tags,'style':style,
                    'image':f'{identifier}.jpg','provenance':provenance(source,second,crop)})
    else:
        folder = ROOT / 'assets/locations' / identifier
        folder.mkdir(parents=True, exist_ok=True)
        image.save(folder / 'bg.jpg', quality=94)
        save_meta(folder, 'location.json', {'id':identifier,'name':label,'bg':'bg.jpg','size':[1920,1080],
                  'floor_y':1005,'char_px_per_unit':0.43,'time_of_day':tod,'signs':[],
                  'profile':{'label':label,'description':', '.join(tags),'tags':tags,'style':style},
                  'provenance':provenance(source,second,crop)})


def character(identifier, label, second, polygon, head_bottom, gender, age, tags,
              *, source=BUNS, full_body=False, style='cutout'):
    image = frame(source,second)
    # Recipes are traced on a 640px review frame. GrabCut refines the uncertain edge.
    factor = image.width/640
    points = np.array([[round(x*factor),round(y*factor)] for x,y in polygon], dtype=np.int32)
    x,y,w,h = cv2.boundingRect(points)
    points -= [x,y]
    rgb = np.asarray(image)[y:y+h,x:x+w].copy()
    poly = np.zeros((h,w),np.uint8)
    cv2.fillPoly(poly,[points],255)
    probable = cv2.dilate(poly,np.ones((7,7),np.uint8))
    sure = cv2.erode(poly,np.ones((17,17),np.uint8))
    mask = np.full((h,w),cv2.GC_BGD,np.uint8)
    mask[probable>0] = cv2.GC_PR_FGD
    mask[sure>0] = cv2.GC_FGD
    if np.any(sure):
        cv2.grabCut(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),mask,None,
                    np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),4,cv2.GC_INIT_WITH_MASK)
    alpha = np.where((mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD),255,0).astype(np.uint8)
    rgba = Image.fromarray(np.dstack([rgb,alpha]),'RGBA')
    scale = 1000/h
    rgba = rgba.resize((max(1,round(w*scale)),1000),Image.Resampling.LANCZOS)
    width = rgba.width
    split = max(80,min(850,round((head_bottom*factor-y)*scale)))
    head = rgba.copy()
    body = rgba.copy()
    head_arr, body_arr = np.array(head), np.array(body)
    head_arr[split+5:,:,3]=0
    body_arr[:split-5,:,3]=0
    folder=ROOT/'assets/characters'/identifier
    folder.mkdir(parents=True,exist_ok=True)
    rgba.save(folder/'preview.png')
    Image.fromarray(body_arr).save(folder/'body.png')
    Image.fromarray(head_arr).save(folder/'head.png')
    actions=['idle','talk','nod','shake_head','scared']
    save_meta(folder,'character.json',{'id':identifier,'height_px':1000,'canvas':[width,1000],
      'image_scale':1,'head_box':[width*.13,0,width*.87,split],
      'bones':{'root':{'parent':None,'pivot':[width/2,1000]},
               'torso':{'parent':'root','pivot':[width/2,800]},
               'head':{'parent':'torso','pivot':[width/2,split]}},
      'parts':[{'name':'body','bone':'torso','offset':[0,0],'image':'body.png','z':0},
               {'name':'head','bone':'head','offset':[0,0],'image':'head.png','z':1}],
      'expressions':{},'profile':{'label':label,'gender':gender,'age':age,
        'description':', '.join(tags),'tags':tags,'style':style,'coverage':'full_body' if full_body else 'portrait',
        'actions':actions,'lipsync':False},'provenance':provenance(source,second,[x,y,x+w,y+h])})


def main():
    # Existing rigged assets are retained, labelled by appearance rather than story identity.
    profiles = {
      'toi':('Nam trẻ · tóc ngắn · áo xanh','male','young',['short black hair','blue long sleeve shirt','normal build','tóc đen ngắn','áo xanh','thanh niên']),
      'chu_tu':('Nam lớn tuổi · hói · tạp dề nâu','male','old',['bald','heavy build','white shirt','brown apron','gold chain','scar','hói','tạp dề','vết sẹo']),
      'co_lan':('Nữ trẻ · tóc dài · váy vàng','female','young',['long dark hair','slim','yellow dress','tóc dài','váy vàng','trẻ tuổi'])}
    for cid,(label,gender,age,tags) in profiles.items():
        path=ROOT/'assets/characters'/cid/'character.json'
        data=json.loads(path.read_text(encoding='utf-8'))
        data['profile']={'label':label,'gender':gender,'age':age,'description':', '.join(tags),
                         'tags':tags,'style':'cutout','coverage':'full_body',
                         'actions':['idle','talk','walk','sit','point','nod','shake_head','scared'],'lipsync':True}
        save_meta(path.parent,'character.json',data)
    # Portraits exclude the subtitle band and the adjacent actor.
    character('nu_tre_ao_xanh','Nữ trẻ · tóc kẹp hồng · áo xanh',95.47,
      [(150,200),(154,128),(164,104),(183,94),(207,94),(225,105),(232,132),(233,186),
       (248,205),(258,258),(270,281),(299,295),(305,310),(243,310),(238,294),(238,312),
       (140,312),(139,225),(143,207)],196,'female','young',['long black hair','pink hair clip','light blue blouse','slim','tóc đen','kẹp hồng','áo xanh nhạt'])
    character('nu_lon_tuoi_ao_tim','Nữ lớn tuổi · tóc bạc búi · áo tím',638.27,
      [(233,312),(235,243),(245,226),(282,220),(292,213),(293,198),(273,174),(265,151),
       (268,119),(282,95),(302,83),(303,66),(312,53),(326,51),(338,60),(340,77),(331,88),
       (355,105),(369,131),(374,154),(365,178),(347,195),(347,214),(359,222),(397,227),(410,244),(410,312)],
      215,'female','old',['grey hair bun','purple blouse','necklace','wrinkles','tóc bạc búi','áo tím','bà lớn tuổi'])
    character('nam_tre_ao_khoac','Nam trẻ · tóc ngắn · áo khoác tối',954.91,
      [(435,188),(448,186),(461,192),(469,205),(469,219),(463,230),(462,244),(466,269),
       (464,307),(464,342),(467,350),(465,354),(449,355),(444,352),(450,344),(451,294),
       (452,280),(451,269),(449,284),(451,302),(443,304),(442,293),(446,273),(448,259),
       (448,250),(436,251),(426,254),(418,253),(418,247),(430,246),(443,247),(447,229),
       (444,223),(437,216),(435,205)],227,'male','young',
      ['short black hair','dark jacket','slim','black pants','tóc ngắn','áo khoác tối','quần đen'],full_body=True)
    character('nu_tre_ao_phan_quang','Nữ trẻ · tóc ngắn · áo phản quang cam',954.91,
      [(143,213),(153,212),(160,216),(164,226),(162,239),(158,243),(158,248),(161,255),
       (162,274),(160,288),(161,295),(157,297),(156,307),(156,341),(162,347),(162,351),
       (147,352),(145,349),(147,342),(147,307),(145,300),(145,287),(142,284),(142,267),
       (141,252),(144,243),(141,235),(140,225)],247,'female','young',
      ['short brown hair','orange safety vest','shorts','white shoes','tóc nâu ngắn','áo phản quang cam','giày trắng'],full_body=True)
    character('nam_truong_thanh_dong_phuc','Nam trưởng thành · đồng phục nâu',1000.14,
      [(210,312),(209,255),(216,239),(245,230),(275,230),(288,220),(290,204),(272,191),
       (261,171),(254,151),(257,131),(263,103),(278,88),(302,81),(324,83),(345,92),
       (358,108),(362,131),(369,146),(366,166),(354,180),(342,195),(338,211),(340,225),
       (354,229),(394,233),(412,242),(419,262),(418,312)],225,'male','adult',
      ['short black hair','brown uniform','gold badge','sad expression','tóc đen ngắn','đồng phục nâu','huy hiệu','nét buồn'])
    plate('hem_thanh_pho_dem','Hẻm thành phố ban đêm',19.48,[0,140,1620,930],['hẻm','phố','đêm','alley','night','city','buildings'],tod='night')
    plate('mat_tien_cua_hang_dem','Mặt tiền cửa hàng đóng cửa',82.24,[0,140,1620,930],['cửa hàng','quán','mặt tiền','đóng cửa','shop','night'],tod='night')
    plate('phong_cua_go','Phòng có cửa gỗ và lịch',593.04,[0,140,1620,900],['phòng','cửa gỗ','lịch','door','room','bedroom'])
    plate('kho_lanh_cong_nghiep','Kho lạnh · tường kim loại',457.34,[0,140,1620,930],['kho lạnh','tủ đông','kim loại','freezer','storage','cold room'])
    plate('bep_quan_an','Bếp quán ăn · kệ bát và bàn',1316.78,[0,250,780,689],['bếp','quán ăn','bát','bàn','kitchen','restaurant'])
    plate('phong_lam_viec','Phòng làm việc · bàn và giấy tờ',1362.01,[0,130,1150,777],['văn phòng','đồn công an','bàn','office','police station','desk'])
    plate('hanh_lang_cua_sat','Hành lang · cửa sắt',1271.54,[30,180,950,698],['hành lang','cũ','cửa','corridor','wall','old building'])
    plate('dien_thoai_tren_tay','Điện thoại cầm trên tay',276.40,[180,100,1600,900],['điện thoại','cuộc gọi','phone','call'],kind='inserts')
    plate('dien_thoai_vo_man_hinh','Điện thoại vỡ màn hình',1045.37,[200,100,1600,890],['điện thoại','vỡ','phone','broken'],kind='inserts')
    plate('cua_kho_lanh','Cửa kho lạnh cận cảnh',457.34,[0,120,1650,900],['cửa','kho lạnh','door','freezer'],kind='inserts')
    plate('khay_dao_bep','Dao bếp trên bàn',1497.71,[10,300,760,722],['dao','bếp','knife','kitchen'],kind='inserts')
    plate('dong_co_hoat_hinh','Đồng cỏ · cây và trời xanh',25.24,[0,0,1920,850],['đồng cỏ','cây','ngoài trời','grass','tree','outdoor'],source=ANTS,tod='day',style='stick')
    plate('duong_que_hoat_hinh','Đường quê · cây và bụi cỏ',36.29,[760,0,1920,650],['đường quê','cỏ','cây','road','countryside'],source=ANTS,tod='day',style='stick')
    plate('nha_go_que','Nhà gỗ ở quê',39.97,[140,0,1880,870],['nhà gỗ','quê','nhà ông bà','wooden house','countryside'],source=ANTS,tod='day',style='stick')
    plate('kien_lua_can_canh','Kiến lửa cận cảnh',23.40,[150,100,1720,880],['kiến lửa','côn trùng','ant','insect'],source=ANTS,kind='inserts',style='stick')
    print('Reference extraction complete: profiles, cutouts, background plates and inserts.',flush=True)


if __name__=='__main__':
    main()
