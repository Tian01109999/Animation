# Hiệu ứng âm thanh (assets/sfx)

`Shot.sfx: ["rain", "door_knock"]` → mixer phát các âm tương ứng trong shot đó.

## Hai loại âm
- **Âm nền (ambience)** — mưa, gió, phố, chợ, quán ăn, côn trùng đêm, phòng máy chủ, quạt, gõ phím…
  Đặt ở mọi shot liên tiếp cùng không gian; mixer gộp thành một đoạn lặp liền mạch, vào/ra mềm và hạ nhỏ
  khi có lời đọc.
- **Âm một lần (oneshot)** — gõ cửa, còi cảnh sát, sấm, tiếng hét, chuông điện thoại, impact… phát một lần
  ở đầu shot.

Danh sách đầy đủ, mô tả "dùng khi nào" và tên đồng nghĩa nằm trong `catalog.json`. AI tách kịch bản chỉ được
chọn tên trong danh sách này; tên lạ bị bỏ khi hậu xử lý. Tên đồng nghĩa được quy đổi
(`knock` → door_knock, `siren` → police_siren, `crickets` → night_insects, `storm` → rain_storm…).

## Nguồn và giấy phép
- 68 âm từ **Freesound.org, chỉ giấy phép CC0**; 3 âm cửa là ghi âm **Public Domain** (PDSounds.org qua
  Wikimedia Commons). `catalog.json` lưu tên gốc, tác giả, giấy phép và trang nguồn từng âm.
- `whoosh`, `impact`, `riser`, `phone_ringtone`, `phone_vibrate` được tổng hợp bằng thuật toán (CC0).

Dựng lại / bổ sung (cần API key Freesound trong `cache/freesound_key.txt` hoặc biến môi trường
`FREESOUND_API_KEY`; thư mục `cache/` không được đóng gói):
`runtime/venv/Scripts/python.exe -X utf8 tools/make_audio_library.py --only sfx`.
Đổi âm chọn chưa hợp: sửa từ khoá trong `FREESOUND_Q` của tool rồi chạy thêm `--redo <key1,key2>`.
Nghe thử toàn bộ: `logs/asset_review/audio_library.html`.

## Thêm âm của bạn
Chép file `assets/sfx/<tên>.ogg` (chữ thường, `_` thay khoảng trắng) và thêm mục vào `sounds` trong
`catalog.json` với `kind` (`oneshot` | `ambience`), `use` (dùng khi nào) và `aliases`.

Mức âm lượng trong `config.yaml`: `audio: {sfx_peak_db: -6, ambience_rms_db: -34, ambience_duck_db: -6}`.
