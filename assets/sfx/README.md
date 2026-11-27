# Hiệu ứng âm thanh (assets/sfx)

`Shot.sfx: ["gong", "wind"]` → mixer phát `assets/sfx/gong.*`, `assets/sfx/wind.*` ở đầu shot.

- Tên file = tên sfx (chữ thường, khoảng trắng thành `_`), đuôi `.wav .ogg .mp3 .flac .m4a .opus`.
- Các file `.ogg` có sẵn được tạo bằng thuật toán (placeholder): gong, heartbeat, door, wind, chop,
  glass_break, footsteps, sizzle, metal_clank, whisper, crowd. Thay bằng file thật cùng tên là xong.
- Tên đồng nghĩa được quy đổi: crowd_night → crowd, knock/creak → door, steps → footsteps, bell → gong,
  glass → glass_break, frying → sizzle, clank → metal_clank ... (xem `SFX_ALIASES` trong mixer.py).
- Tên không có file và không tạo được (vd `scream`) sẽ bị bỏ qua kèm cảnh báo trong log.
- Nguồn gợi ý: freesound.org (lọc CC0), pixabay.com/sound-effects, YouTube Audio Library.
