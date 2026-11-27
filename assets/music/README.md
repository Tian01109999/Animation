# Nhạc nền (assets/music)

Mixer (`storytoon/audio/mixer.py`) chọn nhạc theo `Shot.music_mood` trong storyboard.

## Đặt tên
- Một file cho mỗi mood: `assets/music/<mood>.<đuôi>` — ví dụ `horror.mp3`, `tense.ogg`, `calm.wav`.
- Hoặc một thư mục: `assets/music/<mood>/` chứa nhiều bài; hiện dùng bài đầu tiên theo thứ tự tên.
- Đuôi hỗ trợ: `.wav .ogg .mp3 .flac .m4a .opus` (ffmpeg giải mã, tự chuyển 48 kHz stereo).
- Mood chuẩn: `calm`, `sad`, `tense`, `horror`, `mystery`. Tên khác được quy đổi
  (`scary/creepy/dark` → horror, `suspense/action` → tense, `happy/peaceful` → calm,
  `mysterious/eerie` → mystery, ...); không quy đổi được thì dùng `mystery`.
- `music_mood: "none"` (hoặc `silence`) trong một shot = tắt nhạc từ shot đó.

## File hiện có
Các file `calm/sad/tense/horror/mystery.ogg` lúc đầu là **nhạc nền tạo bằng thuật toán** (drone tối,
lặp liền mạch 32 giây) chỉ để bản demo có tiếng. Muốn thay: xoá file `.ogg` tương ứng và chép bài thật
vào với cùng tên mood. File của bạn không bao giờ bị ghi đè; chỉ file thiếu mới được tạo lại.

## Lấy nhạc ở đâu (miễn phí bản quyền — kiểm tra điều khoản từng bài trước khi đăng YouTube)
- YouTube Audio Library (studio.youtube.com → Thư viện âm thanh): lọc thể loại Cinematic / Ambient, tâm trạng Dark.
- Pixabay Music (pixabay.com/music) — giấy phép Pixabay, không cần ghi nguồn.
- Incompetech (Kevin MacLeod) — CC BY 4.0, phải ghi nguồn trong mô tả video.
- Freesound.org — lọc giấy phép CC0.

## Mức âm lượng
Mixer tự chuẩn hoá nhạc về RMS khoảng −30 dBFS và hạ thêm 12 dB khi có lời thoại. Có thể chỉnh trong
`config.yaml`:
```yaml
audio:
  music_rms_db: -30
  duck_db: -12
  sfx_peak_db: -6
  crossfade_s: 1.5
```
Nên dùng bài có đoạn đầu và cuối nhẹ nhàng; bài ngắn hơn cảnh sẽ được lặp lại, nối bằng crossfade 0.5 giây.
