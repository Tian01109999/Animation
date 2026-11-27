# StoryToon — đặc tả kỹ thuật (MVP)

App portable trên Windows: nhập kịch bản tiếng Việt → phim hoạt hình 2D kiểu "Real Lens / Sigma Lens"
(truyện kể kinh dị/bí ẩn, nền vẽ chi tiết tông trầm, nhân vật vector phẳng dạng cutout puppet,
phụ đề chữ to giữa-dưới, thẻ tên, thẻ địa điểm/giờ, thẻ chương, thẻ luật, vignette + grain).

Máy đích: i5-12400F, RTX 3060 12GB, RAM 16GB, Windows 11. Python venv: `runtime\venv` (Python 3.13).
Chạy mọi thứ bằng `runtime\venv\Scripts\python.exe`. Tất cả đường dẫn tương đối theo gốc app (thư mục chứa `storytoon\`).
Gốc app có dấu tiếng Việt trong path (`d:\Làm việc\Animation`) → luôn dùng `pathlib`, UTF-8, không dùng đường dẫn 8.3.

## Cấu trúc thư mục

```
storytoon/                 package Python
  __init__.py
  config.py                đọc config.yaml + biến môi trường (GEMINI_API_KEY)
  paths.py                 ROOT, ASSETS, PROJECTS, RUNTIME ... (pathlib)
  schema.py                pydantic models (dưới đây) — NGUỒN SỰ THẬT DUY NHẤT
  script/                  Gemini: kịch bản → Storyboard
  imagegen/                provider tạo ảnh: base.py, flow.py (Google Flow qua Playwright), mock.py
  audio/                   tts.py (edge-tts MVP), lipsync.py (Rhubarb), timing
  render/                  puppet rig, actions, camera, overlays, compositor, ffmpeg
  pipeline.py              chạy các bước, resumable
  cli.py                   `python -m storytoon.cli <lệnh>`
  ui.py                    Gradio
assets/
  characters/<id>/character.json + parts/*.png    (puppet)
  parts_library/           bộ phận dùng chung (nếu có)
  actions/<name>.json      keyframe động tác
  locations/<id>/location.json + bg.png
  inserts/                 ảnh chèn
  fonts/                   font hỗ trợ tiếng Việt (Be Vietnam Pro)
  sfx/  music/
projects/<slug>/
  script.txt  storyboard.json  audio/  lipsync/  frames_cache/  shots/  final.mp4  log.txt
runtime/
  venv/  rhubarb/  chrome-profile/  ffmpeg (dùng ffmpeg trong PATH nếu runtime/ffmpeg không có)
config.yaml
```

## schema.py (pydantic v2)

```python
Framing = Literal["wide", "medium", "close", "extreme_close"]
CameraMove = Literal["static", "zoom_in", "zoom_out", "pan_left", "pan_right", "push_in_slow", "shake"]
OverlayKind = Literal["nametag", "location_card", "chapter_card", "rule_card", "time_card"]

class Overlay(BaseModel):
    kind: OverlayKind
    title: str                    # vd tên nhân vật / "Chợ Lớn · Sài Gòn" / "Chương 2"
    subtitle: str | None = None   # vd vai trò / giờ / "Luật số 1"
    character_id: str | None = None   # cho nametag: neo cạnh nhân vật

class CharacterInShot(BaseModel):
    id: str                       # khớp Character.id
    slot: str                     # tên slot đứng/ngồi trong Location (vd "left", "center", "counter")
    action: str = "idle"          # tên trong assets/actions (idle, talk, walk, sit, point, ...)
    expression: str = "neutral"   # neutral, happy, sad, angry, scared, evil, surprised
    facing: Literal["left", "right"] = "right"
    prop: str | None = None

class Line(BaseModel):
    speaker: str                  # "narrator" hoặc Character.id
    text: str                     # tiếng Việt
    # điền bởi bước audio:
    audio: str | None = None      # đường dẫn tương đối trong project
    start: float | None = None    # giây, tương đối đầu shot
    duration: float | None = None
    visemes: list[tuple[float, str]] | None = None   # (giây tương đối đầu line, A..H/X) từ Rhubarb

class Shot(BaseModel):
    id: str                       # "s001"
    location: str                 # Location.id hoặc "insert:<id>"
    framing: Framing = "medium"
    camera: CameraMove = "static"
    focus: str | None = None      # character id camera hướng vào (cho close)
    characters: list[CharacterInShot] = []
    lines: list[Line] = []        # thường 1 line; nhiều line nối tiếp
    subtitle: str | None = None   # mặc định = text các line; ngắn gọn
    overlays: list[Overlay] = []
    sfx: list[str] = []
    music_mood: str | None = None # "tense", "calm", "horror", "sad", None = giữ nhạc trước
    min_duration: float = 2.5
    duration: float | None = None # điền bởi bước audio = max(min_duration, tổng audio + 0.4)

class CharacterDef(BaseModel):      # trong storyboard
    id: str; name: str; role: str   # role hiển thị trên nametag
    description: str                # ngoại hình, để tạo/chọn puppet
    gender: Literal["male", "female"]; age: Literal["child", "young", "adult", "old"]
    voice: str | None = None        # edge-tts voice, vd "vi-VN-NamMinhNeural"

class LocationDef(BaseModel):
    id: str; name: str
    description: str                # mô tả để sinh prompt ảnh nền
    time_of_day: Literal["day", "night", "dusk", "indoor"] = "day"
    signs: list[str] = []           # chữ biển hiệu (render thành lớp text, KHÔNG để AI vẽ chữ)

class Storyboard(BaseModel):
    title: str
    style: str = "realLens"
    characters: list[CharacterDef]
    locations: list[LocationDef]
    shots: list[Shot]
```

## Tài sản

### Character (`assets/characters/<id>/character.json`)
Puppet cutout, mỗi bộ phận 1 PNG RGBA, hệ toạ độ pixel của "canvas nhân vật" cao ~1000px (chân ở y=1000).
```json
{
  "id": "bac_hai", "height_px": 1000,
  "bones": {                       // cây xương, pivot theo toạ độ canvas
    "root":  {"parent": null,   "pivot": [250, 1000]},
    "hip":   {"parent": "root", "pivot": [250, 560]},
    "torso": {"parent": "hip",  "pivot": [250, 560]},
    "neck":  {"parent": "torso","pivot": [250, 300]},
    "head":  {"parent": "neck", "pivot": [250, 290]},
    "arm_l_up": {"parent": "torso", "pivot": [...]}, "arm_l_low": {...}, "hand_l": {...},
    "arm_r_up": {...}, "arm_r_low": {...}, "hand_r": {...},
    "leg_l_up": {...}, "leg_l_low": {...}, "leg_r_up": {...}, "leg_r_low": {...}
  },
  "parts": [                       // thứ tự vẽ = thứ tự mảng (sau cùng ở trên)
    {"bone": "arm_r_up", "image": "parts/arm_r_up.png", "offset": [x, y], "z": 0},
    ...
    {"bone": "head", "image": "parts/head.png", "offset": [x, y]},
    {"bone": "head", "slot": "eyes",  "images": {"open": "...", "half": "...", "closed": "..."}, "offset": [...]},
    {"bone": "head", "slot": "brows", "images": {"neutral": "...", "angry": "...", "sad": "...", "evil": "...", "surprised": "..."}, "offset": [...]},
    {"bone": "head", "slot": "mouth", "images": {"A": "...", "B": "...", ..., "H": "...", "X": "..."}, "offset": [...]}
  ],
  "expressions": {"angry": {"brows": "angry", "eyes": "half"}, ...},
  "hand_prop_anchor": {"bone": "hand_r", "point": [x, y]}
}
```
`offset` = vị trí góc trên-trái ảnh bộ phận trong canvas nhân vật ở tư thế nghỉ (mọi góc xương = 0).

### Action (`assets/actions/<name>.json`)
```json
{"name": "talk", "loop": true, "duration": 2.0,
 "tracks": {"head": [[0, 0], [0.5, 3], [1.0, -2], [2.0, 0]],   // [giây, độ xoay]
            "arm_r_up": [[0, 0], [1, -15], [2, 0]],
            "root.y": [[0, 0], [1, -4], [2, 0]]}}              // dịch chuyển px
```
Nội suy ease-in-out. Mọi action cộng thêm "breathing" (torso scale/translate nhẹ) + chớp mắt ngẫu nhiên (seed theo shot id).
Action tối thiểu MVP: idle, talk, walk (tại chỗ + trượt root.x), sit, point, nod, shake_head, scared.

### Location (`assets/locations/<id>/location.json`)
```json
{"id": "cho_lon", "bg": "bg.png", "size": [3840, 2160],
 "floor_y": 1800,                                   // đường sàn mặc định
 "slots": {"left": {"x": 900, "y": 1820, "scale": 1.0},
           "center": {"x": 1920, "y": 1820, "scale": 1.0},
           "right": {"x": 2900, "y": 1820, "scale": 1.0},
           "counter": {"x": 2200, "y": 1700, "scale": 0.9}},
 "signs": [{"text": "CƠM GÀ BÁC HAI", "box": [1500, 600, 2300, 760], "style": "red_board"}],
 "time_of_day": "day"}
```
Framing → vùng cắt trên nền: wide = toàn ảnh, medium ≈ 55%, close ≈ 30% quanh nhân vật focus (nền blur thêm), extreme_close ≈ 20%.

## Giao diện module

```python
# storytoon/script/breakdown.py
def breakdown(script_text: str, *, existing_characters: list[str], existing_locations: list[str],
              model: str = "gemini-2.5-flash") -> Storyboard
# Gemini structured output (response_schema / response_json_schema). Kịch bản dài → chia đoạn (chapter)
# rồi gộp, giữ nhất quán id nhân vật/địa điểm. Có retry khi JSON không hợp lệ.

# storytoon/imagegen/base.py
class ImageRequest(BaseModel):
    job_id: str; prompt: str; aspect: Literal["16:9","9:16","1:1","4:3","3:4"] = "16:9"
    count: int = 1; reference_images: list[Path] = []; model: str | None = None
    out_dir: Path
class ImageProvider(Protocol):
    def generate(self, req: ImageRequest) -> list[Path]: ...
# flow.py: FlowProvider (Google Flow, Chrome + Playwright CDP). mock.py: MockProvider (ảnh placeholder bằng PIL).

# storytoon/audio/tts.py
def synth_line(text: str, voice: str, out_path: Path) -> float   # trả về duration giây (wav 48k mono)
# storytoon/audio/lipsync.py
def visemes_for(wav: Path, text: str) -> list[tuple[float, str]] # Rhubarb (runtime/rhubarb), fallback: biên độ

# storytoon/render/
def render_shot(shot: Shot, sb: Storyboard, project_dir: Path, out_mp4: Path, *, width=1920, height=1080, fps=30) -> Path
def render_film(sb: Storyboard, project_dir: Path, out_mp4: Path, **kw) -> Path   # ghép shot + audio + nhạc + sfx
```

## Phong cách hình ảnh (bắt chước video mẫu)

- Phụ đề: chữ trắng đậm, viền/bóng đen mềm, giữa-dưới (~88% chiều cao), cỡ ~4.2% chiều cao khung hình, tối đa 2 dòng.
- Nametag: thẻ bo góc trắng ngà, chấm xanh lá bên trái, tên đậm + vai trò nhỏ màu xám, xuất hiện cạnh nhân vật, fade-in 0.3s.
- Location/time card: góc trên-trái, nền nâu-đỏ đậm viền nhạt, chữ trắng nhỏ, chấm đỏ.
- Chapter card: giữa khung, bảng tối có viền vàng, tên phim lớn + số chương trong ô đỏ + phụ đề vàng.
- Rule card: thẻ trắng ngà góc trên-trái, nhãn đỏ nhỏ "Luật số N" + dòng chữ đậm, từ khoá tô đỏ.
- Watermark tên kênh mờ góc trên-phải (cấu hình được, mặc định "StoryToon").
- Hậu kỳ: vignette mạnh, film grain nhẹ, tông màu ấm/trầm; đêm thì tối và lạnh hơn.
- Font: Be Vietnam Pro (tải vào assets/fonts). Text luôn chuẩn hoá NFC.

## Google Flow provider (imagegen/flow.py)

1. Đảm bảo Chrome chạy với `--remote-debugging-port=9222 --user-data-dir=runtime/chrome-profile` (Chrome mới không cho CDP trên profile mặc định). Nếu chưa chạy thì tự khởi động.
2. Playwright `connect_over_cdp`. Kiểm tra phiên Google: nếu bị chuyển tới accounts.google.com → dừng, báo người dùng đăng nhập (raise `LoginRequired`).
3. Mở project (URL trong config.yaml: `flow.project_url`, tên mặc định "Auto Puppet Studio").
4. Chuyển sang chế độ Image; chọn model, tỷ lệ, số lượng.
5. Tải ảnh tham chiếu (nếu có). 6. Dán prompt. 7. Nhấn Generate Image.
8. Chờ đủ số ảnh mới (timeout cấu hình, mặc định 180s), tối đa 2 lần thử lại.
9. Gom ảnh vào Collection của job. 10. Tải về → `out_dir`, ghi `asset.json` (prompt, model, thời điểm). Có phương án dự phòng tải trực tiếp từng ảnh.
- MỌI selector nằm trong `storytoon/imagegen/flow_selectors.json` (ưu tiên role + accessible name/text, hỗ trợ cả nhãn tiếng Việt và tiếng Anh), không hardcode trong code.
- Nhịp như người dùng: khoảng nghỉ giữa các job (mặc định 20–40s), giới hạn số ảnh/ngày (config). KHÔNG dùng kỹ thuật né phát hiện bot.
- Khi lỗi: chụp màn hình + dump accessibility tree vào `logs/flow/<job_id>/`.
- `flow_recon.py`: lệnh khảo sát giao diện — mở project, ở mỗi bước chụp màn hình + lưu aria snapshot, để hiệu chỉnh selector.
- Hàng đợi job: `runtime/jobs.sqlite` (resumable).
