# storytoon.imagegen — tạo ảnh (Google Flow / Mock)

## Dùng nhanh
```python
from storytoon.imagegen import ImageRequest, get_provider
from storytoon.imagegen.queue import JobQueue, run_queue, default_out_dir
from storytoon.imagegen import prompts, library

q = JobQueue()                                   # runtime/jobs.sqlite
req = ImageRequest(job_id="loc_cho_lon", prompt=prompts.background_prompt(loc),
                   aspect="16:9", count=2, reference_images=[style_png], out_dir=default_out_dir("loc_cho_lon"))
q.enqueue(req, tags=["background", "cho_lon"])
summary = run_queue(get_provider())              # theo config image_provider: flow | mock
bg = library.chosen_path("loc_cho_lon")          # ảnh được chọn (hoặc ảnh đầu)
```

## Tệp
| Tệp | Vai trò |
|---|---|
| base.py | `ImageRequest`, `ImageProvider`, `get_provider()`, lỗi `ImageGenError` / `LoginRequired` / `DailyLimitReached` |
| mock.py | `MockProvider` — ảnh placeholder PIL, chạy offline |
| flow.py | `FlowProvider` — 10 bước trên Google Flow; `FlowSettings`, `DailyUsage` (runtime/flow_usage.json) |
| chrome.py | khởi động Chrome (`--remote-debugging-port`, `runtime/chrome-profile`), `connect()` qua CDP |
| resolver.py | `SelectorResolver` — đọc flow_selectors.json, thử nhiều chiến lược, log cái khớp |
| flow_selectors.json | MỌI selector (CHƯA hiệu chỉnh với Flow thật) |
| debug.py | `dump_page()` — ảnh chụp + aria snapshot + danh sách control + HTML + selector report |
| flow_recon.py | lệnh khảo sát giao diện |
| queue.py | `JobQueue` (sqlite) + `run_queue()` |
| library.py | Asset Library `assets/library/<job_id>/` + `index.json` (tags, prompt, source, created, chosen) |
| prompts.py | prompt nền / nhân vật / bộ phận / mặt / ảnh chèn theo phong cách kênh, không bao giờ xin AI vẽ chữ |

## Hiệu chỉnh selector với Flow thật
1. `runtime\venv\Scripts\python.exe -m storytoon.imagegen.flow_recon` (thêm `--generate` để thử tạo 1 ảnh thật).
2. Lần đầu: đăng nhập Google trong cửa sổ Chrome vừa mở (profile riêng `runtime\chrome-profile`), rồi Enter.
3. Ở mỗi bước, nếu tự động không tìm thấy, tự bấm trên Chrome rồi Enter. Kết quả nằm ở `logs\flow_recon\<thời điểm>\`.
4. Đọc `*.controls.txt` / `*.aria.yaml` / `*.selector_report.json`, sửa `flow_selectors.json`.

## Config (config.yaml > flow) — khoá tuỳ chọn mới
- `use_collection` (mặc định true): bước 9–10 qua Collection; lỗi thì tự tải từng ảnh.
- `min_result_px` (mặc định 256): ảnh nhỏ hơn bị coi là icon, không tính là kết quả.

Lỗi luôn lưu chụp màn hình + aria snapshot vào `logs\flow\<job_id>\`.
Collection trên Flow được đặt tên `<job_id>-<yyMMdd-HHmmss>` (mỗi lần chạy một tên) để job chạy lại không tải nhầm ảnh cũ.
Hạn mức `flow.max_images_per_day` đếm theo MỖI lần nhấn Generate (count ảnh/lần), kể cả lần lỗi.
