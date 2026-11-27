# Bộ Tạo Giọng CapCut TTS Độc Lập (1 Quốc Gia Cố Định)

Mã nguồn tạo giọng nói **CapCut TTS** tách riêng hoàn toàn khỏi phần mềm chính:
- **Thuần Node.js (`0` thư viện ngoài)**: chỉ dùng các mô-đun có sẵn của Node.js (`https`, `crypto`, `fs`, `child_process`).
- **Không xoay quốc gia**: đã lược bỏ hoàn toàn mảng 15 vùng và bộ xoay vùng dự phòng; mọi lượt gọi chỉ đi cố định **1 quốc gia duy nhất** (mặc định `VN`, có thể đặt qua `CAPCUT_REGION` hoặc tham số `region`).
- **Đầy đủ kho giọng**: `voices/vi.json` (32 giọng Tiếng Việt), `voices/th.json` (3 giọng Tiếng Thái), `voices/ko.json` (3 giọng Tiếng Hàn).

---

## Cấu trúc thư mục

- `capcut_tts.js`: Toàn bộ lõi ký RSA/MD5, gửi lô SSML, tải MP3, cắt khoảng lặng và giải mã WAV PCM.
- `voices/vi.json`, `voices/th.json`, `voices/ko.json`: Danh mục mã giọng và `resourceId`.
- `cli.js`: Công cụ chạy thử trực tiếp từ dòng lệnh.
- `test/capcut_tts.test.js`: Bộ kiểm thử tự động xác minh cố định 1 quốc gia & xuất âm thanh thật.

---

## Cách dùng trong code Node.js

```js
const capcutTts = require('./capcut_tts');

// 1. Lấy Buffer MP3 trực tiếp (cố định 1 quốc gia 'VN')
const kq = await capcutTts.taoGiong({
  text: 'Xin chào, đây là giọng đọc tạo trực tiếp từ CapCut.',
  voice: 'BV075_streaming',
  lang: 'vi',
  needTimestamp: true,
});
// kq.mp3Buffer, kq.durationMs, kq.words, kq.region ('VN')

// 2. Xuất thẳng ra tệp .mp3 hoặc .wav (tự cắt khoảng lặng đầu/cuối nếu xuất .wav)
await capcutTts.taoGiongRaTep({
  text: 'Câu thoại xuất thẳng ra tệp âm thanh.',
  voice: 'BV075_streaming',
  lang: 'vi',
  outPath: './output.mp3',
});

// 3. Chạy song song nhiều phân đoạn kịch bản
await capcutTts.taoNhieuDoanSongSong({
  items: [
    { text: 'Phân đoạn mở đầu câu chuyện.', clipPath: './clips/seg_000.mp3' },
    { text: 'Phân đoạn tiếp theo kịch tính hơn.', clipPath: './clips/seg_001.mp3' },
  ],
  voiceId: 'BV075_streaming',
  lang: 'vi',
});
```

---

## Chạy thử bằng dòng lệnh (CLI)

```powershell
# Xem danh sách giọng Tiếng Việt / Thái / Hàn
node cli.js --list vi

# Tạo tệp MP3
node cli.js --text "Xin chào các bạn" --voice BV075_streaming --out thu_nghiem.mp3
```
