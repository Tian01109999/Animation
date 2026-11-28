"""Build the music + sound-effect library (assets/music, assets/sfx) from CC0 / public-domain sources.

Every source file comes from Wikimedia Commons; its license is re-checked through the Commons API
before use and stored in the catalog (author, license, page). Sounds that have no good free source
(whoosh, impact, riser, mobile ringtone, vibration) are synthesised here.

    runtime/venv/Scripts/python.exe -X utf8 tools/make_audio_library.py [--only music|sfx] [--force]

Outputs:
    assets/music/<mood>/<slug>.ogg   + assets/music/catalog.json
    assets/sfx/<key>.ogg             + assets/sfx/catalog.json
Downloads are cached in cache/audio-sources/.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storytoon.audio import audio_io  # noqa: E402
from storytoon.tools_bin import add_bundled_to_path  # noqa: E402

SR = audio_io.SR
MUSIC_DIR = ROOT / 'assets' / 'music'
SFX_DIR = ROOT / 'assets' / 'sfx'
CACHE = ROOT / 'cache' / 'audio-sources'
API = 'https://commons.wikimedia.org/w/api.php'
UA = 'StoryToonAssetBuilder/1.0 (CC0 audio library; python-urllib)'
FREE = re.compile(r'^(cc0|public domain|pd\b|pd-|cc-zero)', re.I)
MUSIC_MAX_S = 180.0

# ---------------------------------------------------------------- music: mood -> (use, [commons files])
MUSIC: dict[str, tuple[str, list[str]]] = {
    'calm': ('Đời thường yên bình: buổi sáng, sinh hoạt hằng ngày, mở đầu nhẹ nhàng, trò chuyện bình thường.', [
        'Rafael Archangel - 07 - Calm Down.ogg', 'Rafael Archangel - 17 - Sleep Time.ogg',
        'John Bartmann - cold-morning-master.ogg', 'Komiku - 57 - Quiet Saturday.ogg']),
    'warm': ('Ấm áp, tình thân, tình bạn, hồi tưởng kỷ niệm đẹp, khoảnh khắc dịu dàng.', [
        'John Bartmann - 19 - Tender Moment.ogg', 'Komiku - 01 - Childhood scene.ogg',
        'John Bartmann - 05 - Home At Last.ogg']),
    'sad': ('Buồn, mất mát, tang thương, hối hận, chia ly, nhân vật khóc.', [
        'Komiku - 32 - Sad walk with sad piano.ogg', 'Rafael Archangel - 13 - Melancholy Tune.ogg',
        'Rafael Archangel - 03 - Forgotten.ogg', 'Rafael Archangel - 02 - Gray.ogg']),
    'mystery': ('Bí ẩn, điều lạ bắt đầu xuất hiện, thắc mắc, quan sát manh mối, chưa nguy hiểm rõ.', [
        'Rafael Archangel - 06 - Thinking.ogg', 'Komiku - 16 - Ambiant Wait.ogg',
        'Komiku - 08 - Ambiant Truth.ogg', 'John Bartmann - enigmatic-needle-master.ogg']),
    'tense': ('Căng thẳng, hồi hộp, nguy hiểm đang đến gần, rình rập, lén lút, đếm ngược.', [
        'Komiku - 12 - Tension.ogg', 'Komiku - 03 - Ambiant Anxiety.ogg',
        'Rafael Archangel - 01 - Rising Danger.ogg', 'John Bartmann - broken-suspense-master.ogg']),
    'horror': ('Kinh dị: ma quỷ, xác chết, cảnh rợn người, thứ không giải thích được trong bóng tối.', [
        'Rafael Krux - Horror Suspense.ogg', 'Kevin MacLeod - Horroriffic.ogg',
        'Komiku - 09 - Ambiant Evil.ogg', 'Rafael Archangel - 08 - Ghosts.ogg',
        'John Bartmann - dark-basement-master.ogg', 'freepd:horror/Footsteps in the Attic.mp3', 'freepd:misc/Dark Hallway.mp3',
        'freepd:horror/Creepy Hallow.mp3']),
    'investigation': ('Điều tra: cảnh sát lấy lời khai, phân tích manh mối, suy luận, truy tìm thủ phạm.', [
        'Komiku - 06 - Action Investigation.ogg', 'Komiku - 02 - Action Time Attack Research.ogg',
        'Komiku - 15 - Ambiant Inconvenient Truth.ogg', 'Rafael Archangel - 11 - Deep Dive.ogg']),
    'action': ('Hành động: rượt đuổi, chạy trốn, ẩu đả, giằng co, chạy đua với thời gian.', [
        'Komiku - 04 - Action Chasing.ogg', 'Komiku - 19 - Action Decisive Move.ogg',
        'freepd:scoring/City Run.mp3', 'freepd:scoring/Action Strike.mp3']),
    'shock': ('Sốc: phát hiện kinh hoàng, cú twist, sự thật được hé lộ, khoảnh khắc chết lặng.', [
        'freepd:horror/Hidden Truth.mp3', 'freepd:horror/Mind Chaos.mp3',
        'freepd:misc/Painful Disorientation.mp3']),
    'hopeful': ('Hy vọng, giải thoát, công lý được thực thi, kết thúc có hậu, nhân vật vượt qua nỗi sợ.', [
        'freepd:misc/Journey of Hope.mp3', 'freepd:misc/Finally See The Light.mp3',
        'freepd:scoring/After the End.mp3']),
    'tech': ('Công nghệ: hacker, máy chủ, dữ liệu, màn hình, camera giám sát, AI, phố đêm hiện đại.', [
        'freepd:misc/Circuit.mp3', 'freepd:electronic/Chronos.mp3',
        'freepd:electronic/3 am West End.mp3', 'freepd:electronic/Space Ambience.mp3']),
}
FREEPD = 'https://archive.org/download/freepd/'
FREEPD_INFO = {'license': 'Public domain (CC0) — FreePD.com', 'author': 'FreePD.com',
               'page': 'https://archive.org/details/freepd'}

# ---------------------------------------------------------------- sfx
# key: (commons file | 'synth', kind, select, seconds, use, aliases)
#   kind: oneshot (phát 1 lần ở đầu shot) | ambience (lặp suốt các shot liên tiếp có cùng tên)
#   select: start (từ tiếng đầu tiên) | loudest (đoạn to nhất) | mid (đoạn giữa)
SFX: dict[str, tuple[str, str, str, float, str, list[str]]] = {
    # cửa
    'door_knock': ('Knocking on wood or door.ogg', 'oneshot', 'start', 4, 'Có người gõ cửa.', ['knock', 'knocking']),
    'door': ('Closing an old door.ogg', 'oneshot', 'start', 5, 'Đóng/mở cửa gỗ bình thường.', ['door_open', 'door_close', 'door_slam']),
    'door_creak': ('Squeaky door.ogg', 'oneshot', 'start', 6, 'Cửa cũ kẽo kẹt mở chậm — nhà hoang, ký túc xá đêm, cảnh rợn.', ['creak', 'squeaky_door']),
    'door_metal': ('Open metallic door.ogg', 'oneshot', 'start', 5, 'Cửa sắt / cửa kho / cửa phòng máy mở.', ['metal_door', 'iron_door']),
    'elevator': ('Elevator door closing.ogg', 'oneshot', 'start', 7, 'Cửa thang máy đóng, thang máy chạy.', ['lift']),
    'footsteps': ('Church people walking steps with reverb.ogg', 'oneshot', 'start', 8, 'Tiếng bước chân vang trong hành lang — ai đó đang đến gần.', ['steps', 'footstep', 'walking']),
    # điện thoại & thiết bị
    'phone_ringtone': ('synth', 'oneshot', 'start', 6, 'Điện thoại di động đổ chuông, cuộc gọi đến.', ['phone', 'ringtone', 'cell_phone', 'mobile_ring']),
    'phone_vibrate': ('synth', 'oneshot', 'start', 3, 'Điện thoại rung trên bàn / trong túi, tin nhắn bí ẩn.', ['vibrate', 'vibration']),
    'phone_ring': ('Telephone.ogg', 'oneshot', 'start', 8, 'Điện thoại bàn kiểu cũ reo (văn phòng, đồn cảnh sát, nhà cũ).', ['telephone', 'landline']),
    'phone_dial': ('DTMF dialing.ogg', 'oneshot', 'start', 5, 'Bấm số gọi điện.', ['dial', 'dialing']),
    'phone_hangup': ('IOS phone disconnect tone.wav', 'oneshot', 'start', 2, 'Đầu dây bên kia cúp máy.', ['hang_up', 'call_end']),
    'notification': ('Simple Happy Beep.ogg', 'oneshot', 'start', 2, 'Thông báo / tin nhắn mới hiện trên điện thoại.', ['message', 'ding', 'sms']),
    'typing': ('Typing medium speed.ogg', 'ambience', 'mid', 15, 'Gõ bàn phím máy tính — hacker, nhân viên văn phòng, tra cứu dữ liệu.', ['keyboard', 'typing_keyboard']),
    'camera_shutter': ('Holga shuttersound.ogg', 'oneshot', 'start', 2, 'Chụp ảnh, chụp hiện trường.', ['photo', 'shutter']),
    'electric_buzz': ('Aggressive electric buzzing.ogg', 'oneshot', 'start', 6, 'Đèn chập chờn, chập điện, mất điện — điềm gở.', ['buzz', 'flicker', 'electric']),
    'static': ('Electronic interference.ogg', 'oneshot', 'start', 8, 'Nhiễu sóng điện thoại/loa/màn hình, thiết bị bị "ma ám".', ['interference', 'glitch']),
    'radio_static': ('Radio short wave frequency.ogg', 'oneshot', 'start', 8, 'Bộ đàm / radio dò sóng rè rè.', ['radio', 'walkie_talkie']),
    'server_room': ('Alien machine room air ducts.ogg', 'ambience', 'mid', 12, 'Tiếng ù máy chủ, phòng máy, trung tâm dữ liệu.', ['server_hum', 'machine_hum', 'data_center']),
    'heart_monitor': ('Heart Monitor Beep--freesound.org.oga', 'ambience', 'mid', 15, 'Máy đo nhịp tim bệnh viện, phòng cấp cứu.', ['hospital', 'ecg']),
    # báo động
    'police_siren': ('American police siren i.ogg', 'oneshot', 'start', 12, 'Còi xe cảnh sát / cứu thương đến hiện trường.', ['siren', 'ambulance', 'police']),
    'alarm': ('Alarm - Collision.ogg', 'oneshot', 'start', 8, 'Còi báo động an ninh / hệ thống báo động khẩn cấp.', ['security_alarm', 'emergency_alarm']),
    'fire_alarm': ('NFPA Fire Alarm.ogg', 'oneshot', 'start', 8, 'Chuông báo cháy tòa nhà.', ['smoke_alarm']),
    'alarm_clock': ('Mechanical Clock Ring (Directory.Audio).mp3', 'oneshot', 'start', 6, 'Đồng hồ báo thức reo buổi sáng.', ['wake_up_alarm']),
    'school_bell': ('Old school bell 1.ogg', 'oneshot', 'start', 8, 'Chuông trường reo, giờ vào/ra lớp.', ['bell_school']),
    'clock_tick': ('Clock ticking.ogg', 'ambience', 'mid', 15, 'Đồng hồ tích tắc trong căn phòng im lặng, chờ đợi, thời gian trôi.', ['ticking', 'clock']),
    # con người
    'scream': ('Piercing shriek.ogg', 'oneshot', 'start', 3, 'Tiếng hét thất thanh khi phát hiện xác / gặp ma.', ['shriek', 'yell']),
    'crying': ('Cry of woman.ogg', 'oneshot', 'start', 10, 'Phụ nữ khóc nức nở.', ['cry', 'sobbing', 'weeping']),
    'baby_cry': ('Baby long wanting cry.ogg', 'oneshot', 'start', 8, 'Tiếng trẻ con khóc (đêm khuya, nhà hoang, ma trẻ con).', ['infant_cry']),
    'breathing': ('Heavy breathing 3.ogg', 'oneshot', 'mid', 10, 'Thở dốc vì sợ hãi / sau khi chạy / trốn trong bóng tối.', ['heavy_breathing', 'panting']),
    'sigh': ('Three sighs.ogg', 'oneshot', 'start', 4, 'Thở dài mệt mỏi, chán nản.', []),
    'cough': ('Man coughing.ogg', 'oneshot', 'start', 4, 'Ho khan, người ốm / già.', []),
    'laughter': ('Laughter.ogg', 'oneshot', 'start', 8, 'Tiếng cười vui vẻ của nhóm bạn.', ['laugh']),
    'evil_laugh': ('Evil laughter.ogg', 'oneshot', 'start', 8, 'Tràng cười ác độc / ma quái.', ['creepy_laugh']),
    'ghost': ('Joseph SARDIN - Fantôme 1.oga', 'oneshot', 'start', 7, 'Tiếng ma rên rỉ, thực thể siêu nhiên xuất hiện.', ['ghost_moan', 'spirit']),
    'monster_growl': ('Monster growls.ogg', 'oneshot', 'loudest', 6, 'Tiếng gầm gừ trầm đục của thứ gì đó trong bóng tối.', ['growl', 'beast']),
    # va chạm & đồ vật
    'thud': ('Dull thud.ogg', 'oneshot', 'start', 1, 'Tiếng đập/va chạm đục: ai đó ngã xuống, vật nặng rơi xuống sàn.',
             ['hit', 'body_fall', 'fall', 'drop', 'object_fall', 'heavy_drop']),
    'metal_clank': ('Metal drop thump.ogg', 'oneshot', 'start', 2, 'Vật kim loại rơi / va đập kim loại.', ['clank', 'metal']),
    'chop': ('Chopping leeks.ogg', 'oneshot', 'start', 4, 'Dao chặt trên thớt (bếp, quán ăn).', ['knife_chop', 'cleaver']),
    'sizzle': ('Frying fries going in and out of oil.ogg', 'ambience', 'mid', 15, 'Chiên xào trong chảo dầu (quán ăn, bếp).', ['frying', 'cooking']),
    'gunshot': ('Gunshots 8.ogg', 'oneshot', 'loudest', 3, 'Tiếng súng nổ.', ['gun', 'shot']),
    'coins': ('Coins dropped on wooden floor.ogg', 'oneshot', 'start', 4, 'Đồng xu rơi / đếm tiền.', ['money', 'coin']),
    'page_turn': ('Turning a page.ogg', 'oneshot', 'start', 3, 'Lật trang sổ / hồ sơ / nhật ký.', ['paper', 'page']),
    'writing': ('Writing with inkpen.ogg', 'ambience', 'mid', 10, 'Viết bút lên giấy (ghi chép lời khai, viết thư).', ['pen', 'write']),
    'gong': ('Gong or bell vibrant.ogg', 'oneshot', 'loudest', 8, 'Chuông/cồng chùa ngân dài — linh thiêng, điềm báo.', ['temple_bell', 'bell']),
    # xe cộ
    'car_start': ('Starting a car and driving.ogg', 'oneshot', 'start', 12, 'Nổ máy xe ô tô rồi chạy đi.', ['car', 'engine']),
    'car_unlock': ('Unlocking a car.ogg', 'oneshot', 'start', 3, 'Bấm khoá mở cửa xe.', []),
    'motorbike': ('Motorbike 2.ogg', 'oneshot', 'start', 12, 'Xe máy chạy ngang qua / nổ máy.', ['motorcycle', 'moped', 'scooter']),
    'helicopter': ('Helicopter over quiet neighbourhood.ogg', 'ambience', 'mid', 20, 'Trực thăng bay trên đầu (truy lùng, cứu hộ).', ['chopper']),
    # thời tiết & thiên nhiên
    'thunder': ('Storm thunderbolts.ogg', 'oneshot', 'loudest', 8, 'Sấm sét nổ — khoảnh khắc kinh hoàng, đêm giông.', ['lightning', 'thunderclap']),
    'rain': ('Rain against the window.ogg', 'ambience', 'mid', 30, 'Mưa rơi ngoài cửa sổ / mái hiên.', ['rainy', 'raining']),
    'rain_storm': ('Rain and thunder (1).ogg', 'ambience', 'mid', 30, 'Mưa giông lớn kèm sấm xa.', ['storm', 'thunderstorm', 'heavy_rain']),
    'wind': ('Howling wind.ogg', 'ambience', 'mid', 30, 'Gió rít — đêm lạnh, nơi hoang vắng, sân thượng.', ['howling_wind', 'windy']),
    'night_insects': ('Country night noise.ogg', 'ambience', 'mid', 30, 'Đêm yên tĩnh có côn trùng kêu (ngoại ô, nông thôn, nghĩa địa).', ['crickets', 'night', 'night_ambience']),
    'cicadas': ('Cicadas in Greece.ogg', 'ambience', 'mid', 25, 'Ve sầu kêu trưa hè nóng nực.', ['cicada', 'summer']),
    'birds_morning': ('Birdsong mild sunny day.ogg', 'ambience', 'mid', 30, 'Chim hót buổi sáng yên bình.', ['birds', 'morning']),
    'rooster': ('Medium rooster crowing.ogg', 'oneshot', 'start', 6, 'Gà gáy sáng ở làng quê.', ['chicken_crow']),
    'dog_bark': ('Dog.ogg', 'oneshot', 'loudest', 6, 'Chó sủa trong đêm / khi có người lạ.', ['dog', 'barking']),
    'owl': ('Joseph SARDIN - Chouette hulotte 2.ogg', 'oneshot', 'start', 8, 'Cú kêu trong đêm — điềm gở.', ['owl_hoot']),
    # không gian
    'city_street': ('Sunday in the city street noise1.ogg', 'ambience', 'mid', 30, 'Đường phố đô thị ban ngày, xe cộ và người qua lại.', ['street', 'city']),
    'traffic': ('Highway from bridge center.ogg', 'ambience', 'mid', 30, 'Dòng xe chạy liên tục trên đường lớn / cầu.', ['highway', 'cars']),
    'crowd': ('Shopping mall less crowded.ogg', 'ambience', 'mid', 30, 'Đông người trong trung tâm thương mại, sảnh, nơi công cộng.', ['crowd_day', 'crowd_night', 'mall', 'murmur']),
    'market': ('Le marche daligre.ogg', 'ambience', 'mid', 30, 'Chợ đông đúc, người mua bán.', ['bazaar']),
    'restaurant': ('Restaurant ambience.ogg', 'ambience', 'mid', 30, 'Quán ăn / nhà hàng có tiếng bát đũa, trò chuyện.', ['cafe', 'diner']),
    'classroom': ('Ambient classroom mono.ogg', 'ambience', 'mid', 30, 'Lớp học, học sinh rì rầm.', ['class', 'school']),
    'cafeteria': ('High school cafeteria.ogg', 'ambience', 'mid', 30, 'Căng tin trường / ký túc xá ồn ào giờ ăn.', ['canteen']),
    'bus': ('Bus drive ambience with talk.ogg', 'ambience', 'mid', 30, 'Ngồi trên xe buýt đang chạy.', ['bus_ride']),
    'train': ('Complete train ride 4 minutes.ogg', 'ambience', 'mid', 30, 'Ngồi trên tàu hoả / tàu điện.', ['train_ride', 'subway']),
    'fan': ('Table ventilator.ogg', 'ambience', 'mid', 20, 'Quạt máy chạy trong phòng trọ / ký túc xá đêm hè.', ['ventilator']),
    'water_tap': ('Faucet water into sink.ogg', 'ambience', 'mid', 15, 'Nước chảy từ vòi (nhà vệ sinh, bồn rửa).', ['faucet', 'sink', 'water']),
    'shower': ('Shower.ogg', 'ambience', 'mid', 20, 'Vòi sen trong phòng tắm.', ['bathroom']),
    # tổng hợp (điện ảnh)
    'whoosh': ('synth', 'oneshot', 'start', 1.2, 'Chuyển cảnh nhanh, vật lao vụt qua.', ['swoosh', 'transition']),
    'impact': ('synth', 'oneshot', 'start', 3, 'Cú "đánh" trầm nhấn mạnh khoảnh khắc kinh hoàng / tiết lộ sự thật.', ['hit_boom', 'boom', 'sting', 'stinger']),
    'riser': ('synth', 'oneshot', 'start', 5, 'Âm dâng dần lên trước khi điều đáng sợ xảy ra.', ['build_up', 'tension_rise']),
}
SFX.update({
    'heartbeat': ('freesound', 'oneshot', 'start', 8, 'Nhịp tim đập dồn dập — sợ hãi tột độ, hồi hộp chờ đợi.', ['heart', 'heart_beat']),
    'whisper': ('freesound', 'oneshot', 'start', 8, 'Tiếng thì thầm ma quái không rõ lời.', ['whispers', 'whispering']),
    'glass_break': ('freesound', 'oneshot', 'start', 4, 'Kính / cửa sổ / ly vỡ.', ['glass', 'glass_shatter', 'window_break']),
})

# Freesound (chỉ CC0): key -> (từ khoá tìm kiếm, thời lượng tối thiểu, tối đa) — giây
FREESOUND_Q: dict[str, tuple[str, float, float]] = {
    'door': ('door close wooden', 1, 6), 'elevator': ('elevator door', 2, 15),
    'footsteps': ('footsteps corridor', 3, 20), 'phone_ring': ('old telephone ring', 3, 20),
    'phone_dial': ('phone dialing tones', 1, 10), 'phone_hangup': ('phone busy tone hang up', 1, 8),
    'notification': ('phone notification message', 0.2, 3), 'typing': ('keyboard typing', 10, 120),
    'camera_shutter': ('camera shutter', 0.2, 3), 'electric_buzz': ('electric buzz flicker', 1, 10),
    'static': ('radio static interference', 2, 20), 'radio_static': ('walkie talkie radio', 1, 15),
    'server_room': ('server room hum', 10, 180), 'heart_monitor': ('heart monitor beep hospital', 5, 60),
    'police_siren': ('police siren passing', 5, 40), 'alarm': ('security alarm', 3, 30),
    'fire_alarm': ('fire alarm bell', 3, 30), 'alarm_clock': ('alarm clock ringing', 2, 20),
    'school_bell': ('school bell ringing', 2, 20), 'clock_tick': ('clock ticking', 5, 120),
    'scream': ('woman scream', 0.5, 5), 'crying': ('woman crying sobbing', 3, 40),
    'baby_cry': ('baby crying', 3, 30), 'breathing': ('scared heavy breathing', 3, 30),
    'sigh': ('sigh', 0.5, 4), 'cough': ('cough', 0.5, 5), 'laughter': ('group laughing', 2, 15),
    'evil_laugh': ('evil laugh', 1, 10), 'ghost': ('ghost moan', 2, 15), 'monster_growl': ('monster growl', 1, 10),
    'thud': ('body fall thud', 0.2, 3), 'heavy_drop': ('heavy object drop floor', 0.3, 4),
    'metal_clank': ('metal clank', 0.2, 4), 'chop': ('knife chopping board', 1, 10),
    'sizzle': ('frying pan sizzle', 5, 60), 'gunshot': ('gunshot', 0.3, 4), 'coins': ('coins drop', 0.5, 5),
    'page_turn': ('page turn', 0.3, 3), 'writing': ('pen writing paper', 3, 30), 'gong': ('temple bell gong', 3, 20),
    'car_start': ('car engine start drive away', 5, 30), 'car_unlock': ('car lock beep', 0.3, 3),
    'motorbike': ('motorbike pass by', 3, 20), 'helicopter': ('helicopter flyby', 10, 90),
    'thunder': ('thunder crack', 2, 15), 'rain': ('rain window', 20, 300),
    'rain_storm': ('thunderstorm heavy rain', 20, 300), 'wind': ('wind howling', 20, 300),
    'night_insects': ('crickets night ambience', 20, 300), 'cicadas': ('cicadas', 10, 300),
    'birds_morning': ('morning birds ambience', 20, 300), 'rooster': ('rooster crowing', 1, 8),
    'dog_bark': ('dog barking', 1, 10), 'owl': ('owl hoot night', 1, 15),
    'city_street': ('city street ambience', 30, 300), 'traffic': ('traffic road ambience', 30, 300),
    'crowd': ('crowd walla indoor', 20, 300), 'market': ('street market crowd ambience', 20, 300),
    'restaurant': ('restaurant ambience', 20, 300), 'classroom': ('classroom ambience students', 20, 300),
    'cafeteria': ('cafeteria ambience', 20, 300), 'bus': ('bus interior ambience', 20, 300),
    'train': ('train interior ambience', 20, 300), 'fan': ('electric fan', 10, 200),
    'water_tap': ('water tap running sink', 5, 60), 'shower': ('shower running', 10, 120),
    'heartbeat': ('heartbeat', 3, 30), 'whisper': ('creepy whisper', 2, 20), 'glass_break': ('glass break', 0.5, 5),
}
FREESOUND_Q.update({   # từ khoá sửa sau lượt rà soát đầu (âm chọn sai ngữ cảnh)
    'static': ('tv static noise', 3, 20), 'radio_static': ('radio static noise', 3, 20),
    'alarm_clock': ('alarm clock beeping', 2, 20), 'breathing': ('frightened breathing', 3, 30),
    'ghost': ('ghost wail', 2, 15), 'heavy_drop': ('heavy box drop', 0.3, 4),
    'metal_clank': ('metal pipe drop', 0.3, 4), 'thunder': ('thunder clap', 4, 20),
    'fan': ('electric fan noise', 10, 200), 'shower': ('shower water running', 10, 120),
    'heartbeat': ('heartbeat fast', 3, 30), 'sizzle': ('frying oil sizzle', 5, 60),
    'phone_hangup': ('phone busy signal', 1, 15), 'police_siren': ('police siren', 5, 40),
})
# key -> thẻ Freesound bắt buộc (lọc chính xác hơn từ khoá)
FREESOUND_TAG = {'sizzle': 'frying', 'shower': 'shower', 'fan': 'fan', 'heartbeat': 'heartbeat',
                 'ghost': 'ghost', 'heavy_drop': 'thud'}
FREESOUND_Q.update({'sizzle': ('sizzle', 5, 60), 'shower': ('shower', 10, 120), 'fan': ('fan room', 10, 200),
                    'heartbeat': ('heartbeat', 3, 30), 'ghost': ('ghost moan', 2, 15), 'heavy_drop': ('box drop', 0.3, 5)})
FREESOUND_TAG.update({'ghost': 'spooky'})
FREESOUND_BLOCK_KEY = {'ghost': ('clown', 'laugh', 'kid', 'child', 'wolf', 'howl'), 'fan': ('computer', 'startup', 'pc ')}
# tên âm chứa các từ này thì bỏ qua (giả giọng bằng miệng, nội dung nhạy cảm, sai ngữ cảnh)
FREESOUND_BLOCK = ('sexual', 'sex ', 'mouth', 'imitat', 'backrooms', 'modem', 'squelch', 'cartoon', 'crash',
                   'meme', 'fart', 'moan sex', 'orgasm', 'footstep', 'beep', 'treasure', 'boiling', 'fridge',
                   'refrigerator')
FREESOUND_API = 'https://freesound.org/apiv2/search/text/'
CC0_URL = 'creativecommons.org/publicdomain/zero/1.0'
SYNTH_FALLBACK_KEEP: tuple[str, ...] = ()   # heartbeat/whisper/glass_break giờ lấy từ Freesound
FALLBACK_INFO = {
    'heartbeat': ('Nhịp tim đập dồn dập — sợ hãi tột độ, hồi hộp chờ đợi.', ['heart', 'heart_beat']),
    'whisper': ('Tiếng thì thầm ma quái không rõ lời.', ['whispers', 'whispering']),
    'glass_break': ('Kính / cửa sổ / ly vỡ.', ['glass', 'glass_shatter', 'window_break']),
}


# ---------------------------------------------------------------- commons
def _api(params: dict) -> dict:
    for attempt in range(6):
        try:
            with urlopen(Request(API + '?' + urlencode(params), headers={'User-Agent': UA}), timeout=60) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001 - 429 / mất kết nối: chờ rồi thử lại
            if attempt < 5:
                time.sleep(10 * (attempt + 1))
                continue
            raise
    return {}


def commons_info(titles: list[str]) -> dict[str, dict]:
    """File title -> {url, license, author, page}. Raises if a file is missing or not CC0/PD."""
    out: dict[str, dict] = {}
    for i in range(0, len(titles), 40):
        batch = titles[i:i + 40]
        data = _api({'action': 'query', 'format': 'json', 'prop': 'imageinfo', 'iiprop': 'url|extmetadata',
                     'iiextmetadatafilter': 'LicenseShortName|Artist', 'titles': '|'.join('File:' + t for t in batch)})
        norm = {n['to']: n['from'] for n in data.get('query', {}).get('normalized', [])}
        for page in data.get('query', {}).get('pages', {}).values():
            name = norm.get(page['title'], page['title'])[5:]
            if 'missing' in page or not page.get('imageinfo'):
                raise SystemExit(f'Commons file missing: {name}')
            info = page['imageinfo'][0]
            meta = info.get('extmetadata') or {}
            lic = (meta.get('LicenseShortName') or {}).get('value', '').strip()
            if not FREE.search(lic):
                raise SystemExit(f'Not CC0/public domain ({lic}): {name}')
            author = re.sub(r'<[^>]+>', '', (meta.get('Artist') or {}).get('value', '')).strip()
            out[name] = {'url': info['url'], 'license': lic, 'author': author[:120],
                         'page': 'https://commons.wikimedia.org/wiki/File:' + quote(name.replace(' ', '_'))}
        time.sleep(1)
    return out


def fetch(name: str, url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / re.sub(r'[^\w.\-]+', '_', name)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for attempt in range(8):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA}), timeout=120) as r:
                data = r.read()
            break
        except Exception as e:  # noqa: BLE001 - 429 / mất kết nối: chờ (theo Retry-After) rồi thử lại
            if attempt >= 7:
                raise
            wait = 60 * (attempt + 1)
            retry_after = getattr(getattr(e, 'headers', None), 'get', lambda *_: None)('Retry-After')
            if retry_after and str(retry_after).isdigit():
                wait = max(int(retry_after) + 5, 30)
            print(f'    chờ {wait}s rồi thử lại ({type(e).__name__}: {str(e)[:60]})', flush=True)
            time.sleep(wait)
    tmp = dest.with_suffix(dest.suffix + '.part')
    tmp.write_bytes(data)
    tmp.replace(dest)
    time.sleep(5)          # tải chậm, tránh bị máy chủ Wikimedia giới hạn
    return dest


# ---------------------------------------------------------------- dsp
def _frames_db(x: np.ndarray, hop: int) -> np.ndarray:
    mono = np.abs(x).max(axis=1)
    n = len(mono) // hop
    return mono[: n * hop].reshape(n, hop).max(axis=1) if n else np.zeros(1)


def trim_edges(x: np.ndarray, keep: float = 0.03) -> np.ndarray:
    hop = SR // 100
    level = _frames_db(x, hop)
    loud = np.flatnonzero(level > max(level.max() * 0.03, 1e-4))
    if not len(loud):
        return x
    a = max(0, loud[0] * hop - int(keep * SR))
    b = min(len(x), (loud[-1] + 1) * hop + int(keep * SR))
    return x[a:b]


def loudest(x: np.ndarray, seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    if len(x) <= n:
        return x
    hop = SR // 20
    e = np.convolve(_frames_db(x, hop) ** 2, np.ones(max(1, n // hop)), 'valid')
    a = int(np.argmax(e)) * hop
    return x[max(0, a - SR // 10): a + n]


def fades(x: np.ndarray, fin: float, fout: float) -> np.ndarray:
    x = x.copy()
    i, o = min(len(x), int(fin * SR)), min(len(x), int(fout * SR))
    if i:
        x[:i] *= np.linspace(0, 1, i, dtype=np.float32)[:, None]
    if o:
        x[len(x) - o:] *= np.linspace(1, 0, o, dtype=np.float32)[:, None]
    return x


def peak_norm(x: np.ndarray, db: float) -> np.ndarray:
    return (x * (10 ** (db / 20) / (np.abs(x).max() + 1e-9))).astype(np.float32)


def rms_norm(x: np.ndarray, db: float) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-9)
    y = x * (10 ** (db / 20) / rms)
    peak = float(np.abs(y).max())
    return (y / peak * 0.95 if peak > 0.95 else y).astype(np.float32)


def encode_ogg(x: np.ndarray, dst: Path, quality: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stoon_audio_') as td:
        wav = audio_io.write_wav(Path(td) / 'x.wav', x)
        tmp = dst.with_name(dst.stem + '.part.ogg')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-c:a', 'libvorbis',
                        '-q:a', str(quality), str(tmp)], check=True)
        tmp.replace(dst)


# ---------------------------------------------------------------- synth
def _t(sec: float) -> np.ndarray:
    return np.arange(int(sec * SR)) / SR


def synth(key: str) -> np.ndarray:
    rng = np.random.default_rng(len(key) * 31)
    if key == 'whoosh':
        t = _t(1.2)
        noise = rng.standard_normal(len(t))
        spec = np.fft.rfft(noise)
        f = np.fft.rfftfreq(len(t), 1 / SR)
        band = np.exp(-((np.log(f + 1) - np.log(1800)) ** 2) / 1.2)
        y = np.fft.irfft(spec * band, len(t))
        env = np.sin(np.pi * np.clip(t / 1.2, 0, 1)) ** 2.5
        pan = np.clip(t / 1.2, 0, 1)
        y = y * env
        return np.stack([y * (1 - pan * 0.7), y * (0.3 + pan * 0.7)], axis=1)
    if key == 'impact':
        t = _t(3.0)
        boom = np.sin(2 * np.pi * (55 * t - 12 * t ** 2 / 2)) * np.exp(-t / 0.9)
        sub = np.sin(2 * np.pi * 38 * t) * np.exp(-t / 1.6) * 0.6
        hit = rng.standard_normal(len(t)) * np.exp(-t / 0.05) * 0.5
        y = boom + sub + hit
        return np.stack([y, y], axis=1)
    if key == 'riser':
        t = _t(5.0)
        x = t / 5.0
        tone = sum(np.sin(2 * np.pi * (f0 * t + (f0 * 3) * t ** 2 / 10)) for f0 in (110, 164.8, 220.5))
        noise = rng.standard_normal(len(t)) * 0.25
        y = (tone * 0.3 + noise) * x ** 2.2
        y[-int(0.04 * SR):] *= np.linspace(1, 0, int(0.04 * SR))
        return np.stack([y, y * 0.95], axis=1)
    if key == 'phone_ringtone':
        notes = [1318.5, 1568.0, 2093.0, 1568.0]   # mi-sol-đô-sol, marimba ngắn
        beat = 0.16
        out = np.zeros(int(6 * SR))
        for rep in range(4):
            base = rep * 1.5
            for k, f0 in enumerate(notes):
                t = _t(0.35)
                tone = (np.sin(2 * np.pi * f0 * t) + 0.35 * np.sin(2 * np.pi * f0 * 4 * t) * np.exp(-t / 0.03))
                tone *= np.exp(-t / 0.12) * np.minimum(1, t / 0.003)
                a = int((base + k * beat) * SR)
                out[a:a + len(tone)] += tone[: len(out) - a]
        return np.stack([out, out], axis=1)
    if key == 'phone_vibrate':
        out = np.zeros(int(3 * SR))
        for start in (0.0, 1.3):
            t = _t(0.75)
            buzz = np.sign(np.sin(2 * np.pi * 150 * t)) * 0.6 + np.sin(2 * np.pi * 300 * t) * 0.3
            buzz += rng.standard_normal(len(t)) * 0.08            # mặt bàn rung lạch cạch
            buzz *= np.minimum(1, t / 0.02) * np.minimum(1, (0.75 - t) / 0.03)
            a = int(start * SR)
            out[a:a + len(buzz)] += buzz
        lp = np.convolve(out, np.ones(8) / 8, 'same')
        return np.stack([lp, lp], axis=1)
    raise KeyError(key)


# ---------------------------------------------------------------- build
def _slug(text: str) -> str:
    text = re.sub(r'\.(ogg|oga|opus|mp3|wav|webm|flac)$', '', text, flags=re.I)
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:60]


def build_music(force: bool, skip_missing: bool = False) -> dict:
    files = [f for _, (_, fs) in MUSIC.items() for f in fs]
    info = commons_info([f for f in files if not f.startswith('freepd:')])
    for f in files:
        if f.startswith('freepd:'):
            info[f] = dict(FREEPD_INFO, url=FREEPD + quote(f[7:]), page=FREEPD_INFO['page'] + '#' + quote(f[7:]))
    catalog: dict = {'schema': 1, 'note': 'Nhạc CC0/Public Domain từ Wikimedia Commons; xem nguồn từng bài.',
                     'moods': {}}
    for mood, (use, names) in MUSIC.items():
        tracks = []
        for name in names:
            meta = info[name]
            dst = MUSIC_DIR / mood / (_slug(name) + '.ogg')
            if skip_missing and not dst.exists():
                print(f'  music {mood:<13} (bỏ qua, chưa tải) {name}', flush=True)
                continue
            if force or not dst.exists():
                x = audio_io.decode(fetch(name, meta['url']), channels=2)
                x = trim_edges(x)
                cut = len(x) > MUSIC_MAX_S * SR
                x = x[: int(MUSIC_MAX_S * SR)]
                x = fades(x, 0.05, 4.0 if cut else 0.5)
                encode_ogg(rms_norm(x, -18), dst, 3)
                print(f'  music {mood:<13} {dst.name}', flush=True)
            title = re.sub(r'\.(ogg|oga|opus|mp3|wav|webm)$', '', name.split('/')[-1])
            if name.startswith('freepd:'):
                title = f'FreePD - {title}'
            tracks.append({'file': f'{mood}/{dst.name}', 'title': title, 'author': meta['author'] or title.split(' - ')[0],
                           'license': meta['license'], 'source': meta['page'],
                           'duration': round(audio_io.wav_duration(dst) if dst.suffix == '.wav' else _dur(dst), 1)})
        catalog['moods'][mood] = {'use': use, 'tracks': tracks}
    return catalog


def _dur(path: Path) -> float:
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def freesound_key() -> str | None:
    import os
    key = os.environ.get('FREESOUND_API_KEY', '').strip()
    path = ROOT / 'cache' / 'freesound_key.txt'
    if not key and path.exists():
        key = path.read_text(encoding='utf-8').strip()
    return key or None


def freesound_pick(token: str, query: str, lo: float, hi: float, tag: str | None = None,
                   block: tuple[str, ...] = ()) -> dict | None:
    """Âm CC0 phù hợp nhất (nhiều lượt tải) cho từ khoá, trong khoảng thời lượng [lo, hi]."""
    flt = f'license:"Creative Commons 0" duration:[{lo} TO {hi}]' + (f' tag:{tag}' if tag else '')
    params = {'query': query, 'token': token, 'page_size': 15, 'sort': 'downloads_desc',
              'filter': flt,
              'fields': 'id,name,username,license,duration,previews,url,avg_rating,num_downloads'}
    for attempt in range(4):
        try:
            with urlopen(Request(FREESOUND_API + '?' + urlencode(params), headers={'User-Agent': UA}),
                         timeout=60) as r:
                data = json.load(r)
            break
        except Exception as e:  # noqa: BLE001
            if '401' in str(e) or '403' in str(e):
                raise SystemExit(f'Freesound từ chối API key ({e}). Kiểm tra lại key.')
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    for s in data.get('results', []):
        if any(word in (s.get('name') or '').lower() for word in FREESOUND_BLOCK + block):
            continue
        if CC0_URL in (s.get('license') or '') and (s.get('previews') or {}).get('preview-hq-ogg'):
            return s
    return None


def _cut(x: np.ndarray, select: str, seconds: float) -> np.ndarray:
    if select == 'loudest':
        return trim_edges(loudest(x, seconds))
    if select == 'mid' and len(x) > seconds * SR * 1.2:
        a = (len(x) - int(seconds * SR)) // 2
        return x[a: a + int(seconds * SR)]
    return trim_edges(x)[: int(seconds * SR)]


def build_sfx(force: bool, allow_commons_download: bool = False, redo: frozenset[str] = frozenset()) -> dict:
    old_path = SFX_DIR / 'catalog.json'
    old = json.loads(old_path.read_text(encoding='utf-8')).get('sounds', {}) if old_path.exists() else {}
    commons_names = sorted({spec[0] for spec in SFX.values() if spec[0] not in ('synth', 'freesound')})
    info = commons_info(commons_names)
    token = freesound_key()
    catalog: dict = {'schema': 1, 'note': 'Hiệu ứng CC0/Public Domain: Freesound (CC0), Wikimedia Commons '
                                          '(PDSounds.org…) và âm tổng hợp; xem nguồn từng âm.', 'sounds': {}}
    missing: list[str] = []
    for key, (name, kind, select, seconds, use, aliases) in SFX.items():
        dst = SFX_DIR / f'{key}.ogg'
        entry = {'file': dst.name, 'kind': kind, 'use': use, 'aliases': aliases}
        if (not force and key not in redo and name != 'synth' and dst.exists() and key in old
                and old[key].get('source')):
            entry['source'] = old[key]['source']           # đã dựng ở lần trước: giữ nguyên
        else:
            src = None
            if name == 'synth':
                x = synth(key).astype(np.float32)
                src = {'generated': True, 'license': 'CC0 (tổng hợp bởi StoryToon)'}
            else:
                cached = CACHE / re.sub(r'[^\w.\-]+', '_', name) if name in info else None
                x = None
                if cached is not None and key not in redo and cached.exists() and cached.stat().st_size > 0:
                    x = audio_io.decode(cached, channels=2)
                    m = info[name]
                    src = {'title': name, 'author': m['author'], 'license': m['license'], 'page': m['page']}
                elif token and key in FREESOUND_Q:
                    q, lo, hi = FREESOUND_Q[key]
                    pick = freesound_pick(token, q, lo, hi, FREESOUND_TAG.get(key), FREESOUND_BLOCK_KEY.get(key, ()))
                    if pick:
                        fname = f'freesound_{pick["id"]}.ogg'
                        x = audio_io.decode(fetch(fname, pick['previews']['preview-hq-ogg']), channels=2)
                        src = {'title': pick['name'], 'author': pick['username'], 'license': 'CC0',
                               'page': pick['url'], 'freesound_id': pick['id']}
                    time.sleep(1.1)                       # giới hạn API Freesound: 60 yêu cầu/phút
                if x is None and name in info and allow_commons_download:
                    x = audio_io.decode(fetch(name, info[name]['url']), channels=2)
                    m = info[name]
                    src = {'title': name, 'author': m['author'], 'license': m['license'], 'page': m['page']}
                if x is None:
                    missing.append(key)
                    print(f'  sfx   {key:<15} (chưa có nguồn — bỏ qua)', flush=True)
                    continue
                x = _cut(x, select, seconds)
            if kind == 'ambience':
                x = rms_norm(fades(x, 0.8, 0.8), -20)
            else:
                x = peak_norm(fades(x, 0.003, min(0.4, len(x) / SR / 4)), -1)
            encode_ogg(x, dst, 4)
            entry['source'] = src
            label = src.get('title') if not src.get('generated') else 'tổng hợp'
            print(f'  sfx   {key:<15} {kind:<8} {len(x) / SR:5.1f}s  {label} ({src.get("author", "")})', flush=True)
        entry['duration'] = round(_dur(dst), 2)
        catalog['sounds'][key] = entry
    if missing:
        print('  thiếu:', ', '.join(missing))
    for key in SYNTH_FALLBACK_KEEP:
        if (SFX_DIR / f'{key}.ogg').exists():
            use, aliases = FALLBACK_INFO[key]
            catalog['sounds'][key] = {'file': f'{key}.ogg', 'kind': 'oneshot', 'use': use, 'aliases': aliases,
                                      'duration': round(_dur(SFX_DIR / f'{key}.ogg'), 2),
                                      'source': {'generated': True, 'license': 'CC0 (tổng hợp bởi StoryToon)'}}
    return catalog


def write_review_page() -> Path:
    """logs/asset_review/audio_library.html: nghe thử từng bài/âm kèm mô tả và nguồn."""
    import html
    out = ROOT / 'logs' / 'asset_review' / 'audio_library.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    rel = '../../assets'
    parts = ['<!doctype html><meta charset="utf-8"><title>StoryToon · Nhạc & hiệu ứng</title><style>'
             'body{font:14px "Segoe UI",sans-serif;background:#141922;color:#e8ecf2;margin:24px auto;max-width:1100px}'
             'h2{color:#bbee8d;margin-top:32px}table{border-collapse:collapse;width:100%}td{padding:6px 8px;'
             'border-bottom:1px solid #2a3344;vertical-align:middle}audio{height:32px;width:300px}.m{color:#9aa6b8;'
             'font-size:12px}a{color:#8cc8ff}</style><h1>Thư viện nhạc nền & hiệu ứng</h1>']
    music = json.loads((MUSIC_DIR / 'catalog.json').read_text(encoding='utf-8')) if (MUSIC_DIR / 'catalog.json').exists() else {}
    for mood, entry in (music.get('moods') or {}).items():
        parts.append(f'<h2>Nhạc · {html.escape(mood)}</h2><p class="m">{html.escape(entry["use"])}</p><table>')
        for t in entry['tracks']:
            parts.append(f'<tr><td>{html.escape(t["title"])}<div class="m">{t["duration"]:.0f}s · {html.escape(t["license"])}'
                         f' · <a href="{t["source"]}">nguồn</a></div></td><td><audio controls preload="none" '
                         f'src="{rel}/music/{t["file"]}"></audio></td></tr>')
        parts.append('</table>')
    sfx = json.loads((SFX_DIR / 'catalog.json').read_text(encoding='utf-8')) if (SFX_DIR / 'catalog.json').exists() else {}
    for kind, label in (('ambience', 'Âm nền (lặp suốt cảnh)'), ('oneshot', 'Âm một lần')):
        parts.append(f'<h2>Hiệu ứng · {label}</h2><table>')
        for key, e in sorted((sfx.get('sounds') or {}).items()):
            if e['kind'] != kind:
                continue
            src = e['source']
            origin = ('tổng hợp' if src.get('generated') else
                      f'<a href="{src["page"]}">{html.escape(src["title"])}</a> · {html.escape(src["license"])}')
            parts.append(f'<tr><td><b>{key}</b><div class="m">{html.escape(e["use"])}<br>tên khác: '
                         f'{html.escape(", ".join(e["aliases"]) or "—")} · {e["duration"]:.1f}s · {origin}</div></td>'
                         f'<td><audio controls preload="none" src="{rel}/sfx/{e["file"]}"></audio></td></tr>')
        parts.append('</table>')
    out.write_text(''.join(parts), encoding='utf-8')
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--only', choices=('music', 'sfx'))
    ap.add_argument('--force', action='store_true', help='re-encode files that already exist')
    ap.add_argument('--skip-missing', action='store_true',
                    help='music: chỉ ghi catalog cho bài đã tải, không tải bài còn thiếu')
    ap.add_argument('--commons-download', action='store_true',
                    help='sfx: tải từ Wikimedia khi Freesound không có (chậm, hay bị giới hạn)')
    ap.add_argument('--redo', help='sfx: danh sách key cần tìm & dựng lại, cách nhau dấu phẩy')
    args = ap.parse_args()
    add_bundled_to_path()
    if args.only in (None, 'music'):
        cat = build_music(args.force, args.skip_missing)
        (MUSIC_DIR / 'catalog.json').write_text(json.dumps(cat, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('music:', {m: len(v['tracks']) for m, v in cat['moods'].items()})
    if args.only in (None, 'sfx'):
        cat = build_sfx(args.force, args.commons_download,
                        frozenset(k.strip() for k in (args.redo or '').split(',') if k.strip()))
        (SFX_DIR / 'catalog.json').write_text(json.dumps(cat, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('sfx:', len(cat['sounds']), 'sounds')
    print('review page:', write_review_page())


if __name__ == '__main__':
    main()
