# Nhạc nền (assets/music)

Mixer (`storytoon/audio/mixer.py`) chọn nhạc theo `Shot.music_mood` trong storyboard.

## Mood và cách dùng
Danh sách mood, mô tả "dùng khi nào" và từng bài nằm trong `catalog.json`. AI tách kịch bản đọc mô tả này
để chọn mood theo cảm xúc câu chuyện:

| mood | dùng khi |
|---|---|
| calm | đời thường yên bình, buổi sáng, sinh hoạt |
| warm | tình thân, tình bạn, hồi tưởng kỷ niệm đẹp |
| sad | mất mát, tang thương, hối hận, chia ly |
| mystery | điều lạ xuất hiện, quan sát manh mối |
| tense | nguy hiểm đến gần, rình rập, đếm ngược |
| horror | ma quỷ, xác chết, cảnh rợn người |
| investigation | cảnh sát lấy lời khai, suy luận, truy tìm thủ phạm |
| action | rượt đuổi, chạy trốn, ẩu đả |
| shock | phát hiện kinh hoàng, cú twist, sự thật hé lộ |
| hopeful | giải thoát, công lý, kết thúc có hậu |
| tech | hacker, máy chủ, dữ liệu, camera giám sát |

Mỗi mood có 3–5 bài trong `assets/music/<mood>/`. Khi một mood xuất hiện nhiều lần trong phim, mixer luân
phiên các bài (bắt đầu từ bài khác nhau tuỳ tên phim) nên phim dài không lặp đi lặp lại một bài.
Tên khác được quy đổi: `scary/creepy/ghost` → horror, `suspense/danger` → tense, `chase/fight` → action,
`police/detective` → investigation, `reveal/twist` → shock, `happy/family` → warm, `ending/relief` → hopeful,
`hacker/cyber` → tech.

## Nguồn và giấy phép
Toàn bộ 45 bài là **CC0 / Public Domain**: lấy từ Wikimedia Commons (Komiku, Rafael Archangel, Rafael Krux,
Kevin MacLeod, John Bartmann) và bản lưu FreePD.com trên Internet Archive. Không bắt buộc ghi nguồn; `catalog.json` lưu tác giả, giấy phép
và trang nguồn của từng bài. Dựng lại / bổ sung bằng:

    runtime/venv/Scripts/python.exe -X utf8 tools/make_audio_library.py --only music

Nghe thử toàn bộ: `logs/asset_review/audio_library.html`.

## Thêm bài của bạn
Chép file vào `assets/music/<mood>/` và thêm mục vào `tracks` của mood đó trong `catalog.json`
(đuôi `.wav .ogg .mp3 .flac .m4a .opus`). Kiểm tra điều khoản bản quyền trước khi đăng video.

## Mức âm lượng
Mixer chuẩn hoá nhạc về RMS khoảng −30 dBFS và hạ thêm 12 dB khi có lời. Chỉnh trong `config.yaml`:
```yaml
audio:
  music_rms_db: -30
  duck_db: -12
  crossfade_s: 1.5
```
