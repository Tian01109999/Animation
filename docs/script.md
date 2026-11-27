# storytoon/script — tách kịch bản bằng Gemini

```python
from storytoon.script import breakdown, storyboard_stats, BreakdownError
sb = breakdown(text, existing_characters=["chu_tu"], existing_locations=["cho_dem"])  # model mặc định: config gemini.model
print(storyboard_stats(sb).summary())
```

CLI: `runtime\venv\Scripts\python.exe -m storytoon.script projects\<slug>\script.txt [-o storyboard.json] [--model M]`
và `... -m storytoon.script projects\demo\storyboard.json --stats-only`.

## Luồng
1. `chunking.split_script` — chia ~3500 ký tự (tối đa 4200), ưu tiên cắt trước tiêu đề chương
   (`Chương N`, `Phần N`, `Chapter N`, `# ...`), không tách tiêu đề khỏi nội dung, câu quá dài cắt theo câu.
2. Mỗi đoạn: `prompts.build_chunk_prompt` (kèm nhân vật/địa điểm đã biết, nhân vật đã có nametag, địa điểm shot cuối,
   số chương/luật đã có, id asset có sẵn) + `SYSTEM_PROMPT`, gọi `client.models.generate_content` với
   `response_mime_type="application/json"` và `response_json_schema` (`llm_schema.py`, suy ra từ `Storyboard`,
   bỏ trường audio, slot/action/music_mood là enum).
3. JSON không hợp lệ (parse/pydantic/shots rỗng) → gửi lại kèm lỗi, tối đa 2 lần. Lỗi API → thử lại 3 lần (5/15/40s).
4. `postprocess.merge_part` gộp đoạn: id → ascii snake_case; nhân vật/địa điểm trùng **tên** được gộp về id đã có.
5. `postprocess.finalize`: đánh số lại `s001..`, tạo định nghĩa stub cho id thiếu, kẹp slot/action/music_mood,
   slot trùng trong shot được xếp lại, focus cho close/extreme_close, subtitle mặc định, sfx/prop → snake_case,
   `min_duration` trong [1.5, 8], voice theo giới tính, nametag đúng 1 lần/nhân vật, NFC mọi chuỗi.

## Từ vựng cố định (`vocab.py`)
| | giá trị |
|---|---|
| slot | `left`, `center`, `right`, `far_left`, `far_right`, `counter` (sau quầy/xe hàng/bàn) |
| action | `idle`, `talk`, `walk`, `sit`, `point`, `nod`, `shake_head`, `scared` |
| expression | `neutral`, `happy`, `sad`, `angry`, `scared`, `evil`, `surprised` |
| music_mood | `calm`, `tense`, `horror`, `sad`, `null` (giữ nhạc trước) |
| speaker | `narrator` hoặc id nhân vật; người kể xuất hiện trong khung có id `toi` |
| voice | narrator & nam `vi-VN-NamMinhNeural`, nữ `vi-VN-HoaiMyNeural` |

## Quy ước overlay (renderer đọc theo quy ước này)
- `nametag`: title = tên, subtitle = vai trò, character_id = id. Mỗi nhân vật 1 lần, ở lần xuất hiện đầu
  (ưu tiên shot không phải wide).
- `location_card`: title = "Chợ Lớn · Sài Gòn", subtitle tuỳ chọn.
- `time_card`: title = "23:48" / "Sáng hôm sau", subtitle tuỳ chọn.
- `chapter_card`: title = "Chương N", subtitle = tên chương. **Tên phim lấy từ `Storyboard.title`.**
- `rule_card`: title = nội dung luật, subtitle = "Luật số N".
- `sfx`: tên snake_case tự do (crowd_night, wind, sizzle, footsteps, heartbeat, metal_clank, whisper, scream ...)
  — module audio nên bỏ qua tên không có file.
- `prop`: tên snake_case tự do (khan, mu_bao_hiem, banh_bao) — renderer nên bỏ qua nếu không có asset.

## Demo
`projects/demo/script.txt` + `projects/demo/storyboard.json` (16 shot, ~1:12 ước tính, `chu_tu` + `toi`,
`cho_dem` + `hem_toi`, đủ 5 loại overlay, 4 framing, 7 camera move, action talk/idle/point/sit/scared/walk).

## Test
`runtime\venv\Scripts\python.exe tests\script_test_breakdown.py` (client giả, không cần API key).
