# storytoon.render — engine dựng hình 2D cutout-puppet

## Dùng trong pipeline
```python
from storytoon.render import render_shot, render_film, make_character

render_shot(shot, sb, project_dir, project_dir / "shots" / f"{shot.id}.mp4")          # 1 shot, không tiếng
render_film(sb, project_dir, project_dir / "final.mp4",
            soundtrack=project_dir / "soundtrack.wav",     # wav đã trộn (audio.mixer.build_soundtrack) hoặc None
            workers=2, progress=lambda done, total, sid: ...)
make_character("bac_hai", {"gender": "male", "age": "old", "hair_style": "bald", "shirt_color": "#ecebe4"})
```
- `render_film` render từng shot ra `projects/<p>/shots/<id>.mp4` + `<id>.hash`; shot không đổi (hash dữ liệu shot,
  nhân vật/địa điểm liên quan, mtime tài sản, tham số render, encoder) thì bỏ qua. Ghép bằng concat demuxer (`-c copy`),
  mux âm thanh AAC 192k (`apad` + `-shortest` → dài đúng bằng video). `force=True` để render lại hết.
- Số frame mỗi shot tính theo mốc tích luỹ (`film.frame_counts`) → tổng thời lượng video = tổng `Shot.duration`,
  khớp `audio.timing.shot_offsets` (không trôi tiếng/hình).
- Thời lượng shot: `Shot.duration` nếu có; nếu không ước lượng theo số chữ (`timing.py`). `Line.start/duration/visemes`
  do bước audio điền; thiếu viseme thì khẩu hình giả theo nhịp.

## Kiến trúc (storytoon/render/)
| file | nội dung |
|---|---|
| `backend.py` | GPU (OpenGL qua cửa sổ glfw ẩn) hoặc CPU; `FrameTarget` = surface khung + bộ đệm numpy |
| `compositor.py` | `ShotRenderer` (dựng sẵn mọi thứ 1 lần/shot), `render_shot` |
| `film.py` | `render_film`, `frame_counts`, `shot_hash` |
| `encode.py` | `FrameWriter` (pipe khung thô → ffmpeg, luồng riêng), `pick_encoder` (NVENC → libx264), `concat_videos` |
| `location.py` | nạp nền/lớp parallax/slot/biển hiệu, `insert:<id>`, nền dự phòng |
| `rig.py` | đọc `character.json`, forward kinematics, vẽ bộ phận bằng ma trận skia |
| `actions.py` | keyframe ease-in-out, thở, chớp mắt (seed theo shot+nhân vật), khẩu hình, biểu cảm, ngồi |
| `camera.py` | framing → vùng cắt, chuyển động camera có easing |
| `overlays.py` | phụ đề, nametag, location/time card, chapter card, rule card, watermark (dựng sẵn RGBA, fade) |
| `post.py` | ma trận màu ngày/đêm/hoàng hôn/trong nhà, vignette, film grain |
| `puppetgen.py` | sinh puppet vector tham số hoá (`CharParams`, `make_character`, `params_from_description`, `PRESETS`) |
| `locgen.py` | sinh nền mẫu `cho_dem`, `hem_toi` (far/mid/near), `make_insert_placeholder` |
| `skutil.py` | tiện ích skia: màu, path, font, ảnh, ngắt dòng |

Thứ tự vẽ mỗi frame: lớp nền far/mid (theo camera, parallax 0.8/1.0) → nhân vật (sắp theo slot.y, bóng đổ, ghế khi
`sit`, `clip_bottom` khi đứng sau quầy) → lớp near (parallax 1.15) → vignette → overlay chữ → grain.
Chỉnh màu được "nướng" vào nền 1 lần/shot và gắn vào Paint của nhân vật (đêm: nhân vật tối hơn ~14%), overlay chữ
không bị chỉnh màu. Nền cận cảnh (close/extreme_close) blur sẵn 1 lần/shot.

## Hiệu năng (i5-12400F + RTX 3060, 1920x1080)
- **Bản skia-python Windows dựng bằng MSVC: raster pipeline CPU rất chậm** (vẽ ảnh xoay, blend mode, màu bán trong
  suốt chậm 50–100 lần; 1 frame ~900 ms). Vì vậy engine vẽ bằng **GPU (OpenGL)**: cần `glfw` (đã cài vào venv).
  Không có GPU/GL → tự rơi về CPU (đúng nhưng ~2–3 fps). `STORYTOON_CPU=1` để ép CPU.
- Đo được: chỉ vẽ ~90–125 fps; vẽ + NVENC + ghi ống ~50–60 fps/shot (shot đầu tiên của tiến trình mất thêm ~1.3 s
  nạp ảnh lên GPU); cả phim mẫu 23.5 s render + ghép trong ~13 s (~53 fps). Chạy lại khi không đổi: 0.5 s.

## Tài sản
- Nhân vật: `assets/characters/<id>/character.json` + `parts/*.png` (theo SPEC; thêm các khoá tuỳ chọn `image_scale`
  (ảnh vẽ gấp 2 lần đơn vị canvas để cận cảnh vẫn nét), `canvas`, `head_box`, `generator`). Slot ảnh: `eyes`
  {open,half,closed}, `brows` {neutral,angry,sad,evil,surprised}, `mouth` {A..H,X}, `hand_l`/`hand_r` {open,point,fist}.
  Quy ước: puppet vẽ nhìn sang phải; `_r` = tay/chân phía xa (vẽ sau thân), `_l` = phía gần. `facing: left` = lật ngang.
- Động tác `assets/actions/*.json` theo SPEC, thêm khoá tuỳ chọn: `slots` (vd `{"hand_r": "point"}`), `move.x_per_s`
  (walk trượt root), `sit: true` (hông tự hạ để chân chạm sàn + vẽ ghế nhựa), `default_expression`.
  Kênh track: `bone` (=xoay độ), `bone.x|y|sx|sy`. Nhân vật `idle` mà có thoại sẽ tự trộn sang `talk` khi nói.
- Địa điểm: `location.json` theo SPEC, thêm tuỳ chọn `layers` {far,mid,near: {image, parallax}}, `slots.*.clip_bottom`,
  `char_px_per_unit` (mặc định 0.8 px nền / đơn vị nhân vật ở scale 1), `lights`. Chỉ có `bg.png` phẳng (ảnh AI) vẫn chạy.
  Biển hiệu `signs[{text, box, style}]` vẽ bằng chữ thật, style: `red_board`, `gold_board`, `cabinet`, `neon`,
  `white_board`, `plain`. Tìm địa điểm ở `projects/<p>/locations/<id>/` trước rồi `assets/locations/<id>/`.
- Ảnh chèn `insert:<id>`: `projects/<p>/inserts/<id>.(png|jpg|jpeg|webp)` hoặc `assets/inserts/`, Ken Burns
  (camera `static` → `push_in_slow`), không vẽ nhân vật.
- Thiếu tài sản không bao giờ làm sập: địa điểm thiếu → nền gradient tối + cảnh báo; nhân vật thiếu → bỏ qua + cảnh báo;
  động tác thiếu → `idle`; slot thiếu → `center` (2 nhân vật cùng slot tự xếp lệch).
- Overlay: `rule_card` tô đỏ từ khoá viết trong `*...*`, `[...]`, `«...»` hoặc ngoặc kép; `subtitle` dùng làm nhãn
  ("Luật số 1"). `chapter_card` lấy `sb.title` làm tên phim. Nametag tự chọn bên đầu nhân vật không đè người khác.
  Watermark: `config.yaml > render.watermark`.

## Tạo lại tài sản mẫu
```
runtime\venv\Scripts\python.exe tools\make_placeholder_assets.py            # tất cả (font, động tác, nhân vật, nền, ảnh chèn)
runtime\venv\Scripts\python.exe tools\make_placeholder_assets.py --chars --only chu_tu
```

## Test
```
runtime\venv\Scripts\python.exe tests\render_smoke.py            # 7 shot + ảnh tĩnh + ghép phim có tiếng -> logs/render_test/
runtime\venv\Scripts\python.exe tests\render_smoke.py --quick    # chỉ ảnh tĩnh + đo fps vẽ
```

## Chưa làm / giới hạn
- `CharacterInShot.prop` chưa vẽ (đã có `hand_prop_anchor` trong character.json).
- Chưa có chuyển cảnh (fade/crossfade) giữa các shot — cắt thẳng.
- `walk` trượt liên tục, không tự dừng ở mép khung.
- Puppet mẫu là placeholder vector; ảnh AI từ Flow sẽ thay nền (`bg.png`), puppet AI cần cắt thành bộ phận theo
  định dạng trên.
