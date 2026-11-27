# Tích hợp: pipeline, CLI, UI, tài khoản

Tài liệu này mô tả các file ghép nối các module của StoryToon, cách chạy lại một phần pipeline, các file đã sửa ở module khác và cách kiểm thử.

## File

| File | Vai trò |
|---|---|
| `storytoon/pipeline.py` | `run(project, steps, *, force, provider, progress, model, workers)`. Cũng chứa `step_breakdown`, `step_assets`, `step_audio`, `step_render`, `render_shots`, `preview_shot`, `new_project`, `list_projects`, `load_storyboard`, `save_storyboard`, `load_render_storyboard`, `install_background`, `puppet_params` và `PipelineError`. |
| `storytoon/cli.py` | `python -m storytoon.cli`. Các lệnh: `new`, `breakdown`, `assets`, `audio`, `render [--shots]`, `run`, `flow-login`, `flow-status`, `flow-recon`, `flow-test`, `queue-run`, `ui`. |
| `storytoon/ui.py` | App Gradio 6, chạy ở 127.0.0.1:7860. Có 5 tab. Việc lâu chạy trong luồng riêng (`_stream`), log được đẩy dần lên giao diện. |
| `storytoon/account.py` | Đăng nhập Flow, `flow_status` (đọc email nếu có), đăng xuất (xoá profile), key Gemini trong `.env`, `save_settings` ghi vào `config.yaml`, `setup_status`. |
| `StoryToon.bat` | File chạy ở gốc app. |
| `README.md` | Hướng dẫn người dùng (tiếng Việt). |

## Dữ liệu project và cơ chế chạy lại

**Hai bản storyboard:**

- `storyboard.json` là bản người dùng sửa tay, **không** chứa dữ liệu âm thanh.
- Bước audio ghi `storyboard.timed.json` (audio, start, duration, visemes) và `soundtrack.wav`.

**Renderer dùng bản timed chỉ khi còn khớp.** Điều kiện khớp là hash trong `state.json > steps.audio.input` bằng hash của `storyboard.json` cộng cấu hình `tts` và `audio`. Nếu không khớp, `step_render` và `render_shots` tự chạy lại bước audio. Việc này nhanh vì TTS và Rhubarb đều có cache.

**Điều kiện bỏ qua từng bước:**

| Bước | Hành vi |
|---|---|
| breakdown | Bỏ qua nếu đã có `storyboard.json`, trừ khi dùng force. Khi chạy lại, file cũ được sao lưu thành `storyboard.bak.json`. |
| assets | Lần nào cũng chạy, vì bước này nhanh. Bước làm những việc sau: |
| | • Tạo puppet tham số cho nhân vật thiếu `assets/characters/<id>`. |
| | • Tạo `location.json` mặc định cho địa điểm chưa có, ở cả `projects/<p>/locations` lẫn `assets/locations`. Có đủ 6 slot, và biển hiệu lấy từ `LocationDef.signs` đặt ở vị trí mặc định. |
| | • Xếp job ảnh nền `bg_<id>` vào `runtime/jobs.sqlite`, chạy hàng đợi, rồi chép ảnh đã chọn thành `bg.<ext>`. |
| audio | Bỏ qua nếu hash đầu vào không đổi. |
| render | `render_film` tự bỏ qua những shot có hash không đổi. `render_shots` cũng ghi file `.hash` để lần render sau dùng lại. |

**Tiến độ:** callback có dạng `progress(step, frac, msg)`, trong đó `frac = -1` nghĩa là không xác định. Mọi dòng tiến độ, cùng cảnh báo của các module `storytoon.*`, được ghi vào `projects/<p>/log.txt`.

## Sửa ở module khác

- **imagegen/chrome.py:**
  - `flow.chrome_path` để trống hoặc trỏ sai thì app tự dò trình duyệt theo thứ tự: Chrome trong Program Files, Program Files (x86), LOCALAPPDATA, rồi Microsoft Edge.
  - Thêm `browser_candidates()` và `browser_name()`.
  - `is_flow_url` nhận thêm `flow.google…`.
- **imagegen/flow.py:** nếu không thấy project tên `flow.project_name` thì tạo mới (`create_project`).
- **imagegen/flow_selectors.json:** thêm hai khoá `new_project_button` và `project_title_input`. Cả hai **chưa** được kiểm tra trên Flow thật.

## Kiểm thử

```
runtime\venv\Scripts\python.exe -m unittest tests.integration_test_pipeline -v
runtime\venv\Scripts\python.exe tests\integration_ui_smoke.py
runtime\venv\Scripts\python.exe -m storytoon.cli run demo --steps assets,audio,render --provider mock
```
