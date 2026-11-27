# storytoon.audio — lồng tiếng, khẩu hình, căn thời gian, trộn âm

## Dùng trong pipeline
```python
from storytoon.audio.timing import fill_timing, shot_offsets, film_duration
from storytoon.audio.mixer import build_soundtrack

sb = fill_timing(sb, project_dir)            # sửa sb tại chỗ; ghi audio/, lipsync/, subtitles.srt
save(sb)                                     # pipeline tự lưu storyboard.json
build_soundtrack(sb, project_dir, project_dir / "soundtrack.wav")   # 48 kHz stereo, dài = film_duration(sb)
```
Sau `fill_timing`: `Line.audio` = đường dẫn tương đối trong project (`audio/s001_00_<hash>.wav`, 48 kHz mono),
`Line.start` tính từ đầu shot (câu đầu 0.25 s, nghỉ 0.15 s giữa câu), `Line.duration`, `Line.visemes`
= `[(giây từ đầu câu, "A".."H"|"X"), ...]`, `Shot.duration = max(min_duration, kết thúc câu cuối + 0.45)`.
Thời điểm tuyệt đối của shot: `shot_offsets(sb)[i]` (renderer và mixer dùng cùng hàm này để khớp nhau).
Viseme là hình miệng có hiệu lực từ thời điểm đó đến cue kế tiếp; sau cue cuối là "X".

## Module
| file | nội dung |
|---|---|
| `tts.py` | `synth_line(text, voice, out_path, *, rate, pitch) -> float`, bản async `synth_line_async`, `TTSEngine` (Edge; F5 = stub), cache theo hash(engine+voice+rate+pitch+text NFC) lưu ở `<wav>.json` |
| `lipsync.py` | `ensure_rhubarb()`, `visemes_for(wav, text)`, `run_rhubarb(wav)`, `amplitude_visemes(wav)` |
| `timing.py` | `fill_timing`, `build_voice_map`, `layout_shot`, `write_srt`, `shot_offsets`, `film_duration` |
| `mixer.py` | `build_soundtrack`, `music_segments`, `duck_gain`, `resolve_music`, `resolve_sfx` |
| `procedural.py` | nhạc drone + sfx tạo bằng numpy khi thiếu file (`ensure_default_assets()`) |
| `audio_io.py` | ffmpeg, đọc/ghi wav, giải mã float32 |

## Giọng
edge-tts chỉ có 2 giọng tiếng Việt (NamMinh nam, HoaiMy nữ). Để phân biệt nhân vật: chỉnh theo tuổi
(child +8%/+30 Hz, young +4%/+8 Hz, old −10%/−10 Hz) và — với nhân vật không chỉ định `voice` — lệch
pitch ±6/±12 Hz giữa các nhân vật trùng giọng gốc + tuổi. Người dẫn chuyện: `tts.narrator_voice`.

## Quyết định về Rhubarb
- Bản 1.14.0 Windows tải tự động vào `runtime/rhubarb/` (dùng API GitHub, lỗi thì URL cố định; mất mạng →
  fallback biên độ, không làm hỏng pipeline).
- Dùng `-r phonetic` (không phụ thuộc ngôn ngữ) + `--extendedShapes GHX`. **Không truyền `--dialogFile`**:
  dialog chỉ có tác dụng với recognizer PocketSphinx (tiếng Anh); với tiếng Việt vô ích hoặc có hại.
- **Rhubarb không chạy được từ đường dẫn có dấu** (lỗi "Could not determine path of bin directory" do
  boost::filesystem). Vì vậy `lipsync.py` tự chép thư mục rhubarb sang `%LOCALAPPDATA%\storytoon\` (một lần)
  và chép wav sang thư mục tạm ASCII trước khi gọi. Gốc app vẫn portable: bản chép tự tạo lại khi thiếu.
- Kết quả Rhubarb được cache ở `projects/<p>/lipsync/<tên wav>.json`; fallback biên độ không cache.

## Sự cố edge-tts đã gặp
Dịch vụ thỉnh thoảng trả "No audio was received" cho một số câu tiếng Việt và lặp lại đúng cho cùng yêu cầu.
`EdgeTTSEngine` thử tới 8 biến thể gần như không nghe ra (volume/pitch/rate ±1, thêm " ," cuối câu),
rồi `synth_line_async` thử lại cả vòng 3 lần. Demo 16 câu: chạy lần đầu ~15–40 s, chạy lại (cache) ~1–2 s.

## Test
```
runtime\venv\Scripts\python.exe -m unittest tests.audio_test_offline     # không cần mạng
runtime\venv\Scripts\python.exe -m unittest tests.audio_test_live        # edge-tts + Rhubarb + projects/demo
```

## Chưa làm
- F5-TTS (stub `F5TTSEngine`), chưa có giọng clone.
- Chưa cắt khoảng lặng đầu/cuối của mp3 edge-tts (~0.1 s) — vô hại, viseme đã tính theo file thật.
- Nhạc trong thư mục `assets/music/<mood>/` mới dùng bài đầu tiên (chưa xoay vòng).
