# Kế hoạch dựng thư viện tài sản gốc (Asset Plan)

Nguồn thiết kế: `docs/STYLE_GUIDE.md` + `assets/catalog/{archetypes,locations,inserts,overlays,effects}.json`.
Schema đã mở rộng (tương thích ngược) trong `storytoon/schema.py`:
`Expression` (+nervous, shocked, crying, tired, smirk), `OverlayKind` (+cctv, phone_chat, phone_bank, missing_poster,
map_card, timeline, info_card, job_ad, rule_list, badge), `Overlay.data`, `Shot.effects`, `Shot.transition`,
`CharacterInShot.pose`/`view`, `CharacterDef.tags`/`archetype`. `Overlay.data` bị loại khỏi JSON schema gửi LLM
(`script/llm_schema.py`) để giữ structured output chặt.

**Quy tắc chung cho cả 3 gói**
- Bản quyền: chỉ phong cách + nguyên mẫu chung. Không tên/logo/thương hiệu/chữ poster của kênh tham khảo; không nhúng
  hay cắt ảnh tham khảo. Thương hiệu cửa hàng hư cấu dùng palette `brand_store` (xanh lục bảo `#1f6f5c` / kem / cam).
- Mọi chữ là text thật (Be Vietnam Pro, NFC), không để AI vẽ chữ.
- Không bao giờ làm sập render: tham số/tên thiếu → bỏ qua + `log.warning`.
- Tài sản sinh ra được `storytoon/asset_library.catalog()` tự phát hiện: nhân vật cần `assets/characters/<id>/character.json`
  (+ khoá `profile` {gender, age, label, description, tags, actions, coverage, lipsync}), địa điểm cần
  `assets/locations/<id>/location.json` (+ `profile`) và `bg`, ảnh chèn là `assets/inserts/<id>.png` + `<id>.json`
  ({label, tags, props, style, provenance: {"kind": "procedural"}}).
- Test của mỗi gói nằm trong file test **riêng** của gói (dưới), không sửa test của gói khác.
- Không gói nào sửa `storytoon/schema.py`, `storytoon/asset_library.py`, `storytoon/pipeline.py`, `assets/catalog/*`
  (đóng băng). Cần đổi hợp đồng → ghi vào mục "Yêu cầu đổi hợp đồng" ở cuối báo cáo, không tự sửa.

---

## Gói A — Nhân vật (characters)

**Sở hữu (chỉ A được ghi):**
- `storytoon/render/puppetgen.py`
- `storytoon/render/rig.py` *(chỉ khi cần cho view back/side; giữ API cũ)*
- `assets/characters/<archetype_id>/**` (mới, 1 thư mục / archetype trong `archetypes.json`)
- `tools/make_archetype_characters.py` (mới)
- `tests/render_test_puppets.py` (mới)

**Việc:**
1. Mở rộng `CharParams`: `hair_style` thêm `spiky`(đã có) `short_side_part`, `buzz`, `curly_short`, `afro_curly`,
   `long_straight`, `long_ponytail`, `bob_bangs`, `long_over_face`, `grey_short`, `cap_hidden`, `none_entity`;
   `outfit_type` theo STYLE_GUIDE §4 (polo_uniform, hoodie, utility_jacket, school_uniform_f/m, floral_blouse, ao_ba_ba,
   ao_dai, hi_vis_vest, police_uniform, security_uniform, nurse_scrubs, monk_robe, long_sheet_shirt...);
   `accessories: list[str]` (glasses_black_rect, reading_glasses_gold_round + eyeglass_chain_dotted,
   gold_chain_square_pendant, cap, backpack_*, prayer_beads, name_badge, store_emblem_leaf...); `eye_bags: bool`,
   `blush: float`, `ghost: Literal[None,"water","pale","frozen","cctv"]` (khử bão hoà + FX); `height_scale` (thực thể cao 1.5).
2. Slot ảnh mới trong `character.json` (giữ slot cũ):
   - `eyes`: + `wide`, `shock` (vòng trắng to, đồng tử nhỏ), `teary`, `happy`.
   - `brows`: giữ 5 trạng thái, thêm `worried_asym` (nervous), `smirk`.
   - `mouth`: giữ `A..H,X`, thêm `flat`, `smile`, `frown`, `wavy`, `wavy_small`, `o_small`, `sob`, `smirk`, `grin`, `shout`.
   - slot FX trên `head` (ẩn mặc định): `fx_sweat`, `fx_dashes`, `fx_tears`, `fx_vein`, `fx_drips`, `fx_eyebags_heavy`.
   - Ảnh `view`: `head_back.png`, `hair_back_view.png`, `torso_back.png` (dùng khi `CharacterInShot.view == "back"`);
     side tạm = front + lật (v1).
3. `expressions` trong `character.json` phủ đủ 12 biểu cảm (`schema.Expression`) theo bảng STYLE_GUIDE §2, gồm khoá
   `mouth` (miệng nghỉ) và `fx: [..]` (slot FX bật). Rig/Animator hiện đã fallback `neutral` cho biểu cảm thiếu.
4. API công khai (C/integration gọi; không đổi chữ ký cũ):
   ```python
   make_character(cid, params) -> Path                          # giữ
   params_from_archetype(archetype: dict) -> CharParams          # mới: đọc 1 mục archetypes.json
   make_archetype(archetype_id: str, out_root=CHARACTERS) -> Path  # mới
   make_all_archetypes(out_root=CHARACTERS) -> list[Path]        # mới
   render_portrait(cid: str, size=(600, 760), expression="neutral") -> skia.Image  # mới: ảnh thẻ cho missing_poster
   render_hand(kind: Literal["open","point","pinch","hold","grip"], sleeve: str, skin: str, scale=1.0) -> skia.Image  # mới: tay POV cho B
   ```
   `params_from_description` thêm nhận diện từ khoá tags (kính, tóc xoăn, mũ, áo phản quang, ma, tóc bob...).
5. Rig: `Rig.draw(..., view="front"|"back")` chọn ảnh back khi có; FX slot bật theo `expressions[expr].fx`.
   Nếu cần đổi `actions.py` (đọc `fx`/`view`), A sở hữu `storytoon/render/actions.py` luôn.
6. Sinh 24 archetype vào `assets/characters/<id>/` với `profile.tags` + `profile.archetype`, `preview.png`.

**Kiểm thử:** `tests/render_test_puppets.py` — mỗi archetype sinh được, đủ ảnh slot, `asset_library.catalog()` thấy
`ready=True`; ảnh preview lưới 12 biểu cảm → `logs/puppets/`.

---

## Gói B — Địa điểm + ảnh chèn (locations + inserts)

**Sở hữu:**
- `storytoon/render/locgen.py`
- `storytoon/render/insertgen.py` (mới)
- `storytoon/render/location.py` *(chỉ phần nạp slot phân số / `mirrored` sign / plate trống; giữ API)*
- `assets/locations/<id>/**` cho 8 id `procedural: true` trong `locations.json`
- `assets/inserts/<id>.png|.json` cho các mục `procedural: true` trong `inserts.json`
- `tools/make_catalog_locations.py` (mới)
- `tests/render_test_locations.py` (mới)

**Việc:**
1. `locgen`: hàm vẽ cho 8 địa điểm procedural — `cua_hang_loi_ke`, `cua_hang_quay_thu_ngan`,
   `cua_hang_cua_kinh_tu_trong`, `cua_hang_mat_tien_dem`, `cua_hang_cua_cuon_dong`, `phong_nhan_vien`,
   `cho_xe_om_ven_duong`, `nen_toi_truu_tuong`. Phong cách STYLE_GUIDE §7 (flat + gradient, "low-poly" = mặt phẳng
   3 tông). Xuất layers far/mid/near khi có tiền cảnh (quầy, tủ đá). Mỗi địa điểm có biến thể `time_variants`
   (vd `<id>` + `<id>__day`), slots đổi từ phân số → px (×3840/×2160), `signs` có `box` px.
2. Hỗ trợ trong `location.json`: `slots.*.clip_bottom` (đã có), `signs[].mirrored` (chữ ngược trên kính), `profile`
   {label, description, kind, tags, time_variants}.
3. `insertgen.py` (mới) — vẽ ảnh chèn 3840×2160 từ params (`inserts.json`):
   `phone_chat`, `phone_lock`, `phone_bank`, `cash_drawer`, `coin_wet`, `banknote_wet`, `rule_paper`, `missing_poster`,
   `map_card`, `wall_clock`, `ledger_book`, `hand_holding_paper`, `wet_footprints`, `prayer_beads`, `taped_notice`,
   `job_ad_card`, `door_chime`, `snack_bag`, `black_frame_text`.
   Tay POV lấy từ `puppetgen.render_hand` (gói A); khi A chưa xong → tay mitten tạm vẽ tại chỗ.
   Ảnh thẻ người dùng `puppetgen.render_portrait` (fallback: ô tròn cam).
4. API công khai:
   ```python
   # locgen
   make_location(lid, out_root=LOCATIONS) -> Path                # giữ; nay nhận cả 8 id mới
   make_catalog_locations(out_root=LOCATIONS) -> list[Path]      # mới
   # insertgen
   INSERTS: dict[str, Callable[[dict, tuple[int,int]], skia.Image]]
   render_insert(kind: str, params: dict | None = None, size=(3840, 2160)) -> skia.Image   # params trộn default
   make_insert(iid: str, kind: str, params: dict | None = None, out_dir=INSERTS_DIR) -> Path  # ghi png + json
   # Phần tử dùng chung (C gọi để vẽ overlay cùng thiết kế):
   draw_phone(c, rect, screen: Literal["chat","lock","bank"], data: dict) -> None
   draw_paper_notebook(c, rect, title, rules, *, red_index=None, redact_last=False, blurred=False) -> None
   draw_missing_poster(c, rect, data: dict) -> None
   draw_map_card(c, rect, data: dict) -> None
   ```
   Các hàm `draw_*` chỉ vẽ lên `skia.Canvas` cho trước, không đọc file, không phụ thuộc Shot.

**Kiểm thử:** `tests/render_test_locations.py` — 8 địa điểm + mọi insert procedural sinh được, `catalog()` thấy
`ready=True`, slot nằm trong khung; ảnh xem trước → `logs/locations/`.

---

## Gói C — Overlay + hiệu ứng + móc compositor

**Sở hữu:**
- `storytoon/render/overlays.py`
- `storytoon/render/post.py`
- `storytoon/render/effects.py` (mới)
- `storytoon/render/compositor.py` (**chỉ C sửa**)
- `storytoon/render/film.py` *(chỉ phần chuyển cảnh nếu cần)*
- `tests/render_test_overlays.py` (mới)

**Việc:**
1. `overlays.py`: `build_overlays` xử lý 10 kind mới theo `overlays.json` (đọc `Overlay.data`, mặc định khi thiếu):
   `cctv` (REC nháy, CAM label, timestamp chạy theo t, hộp đếm người, `people_emphasis`), `phone_chat`, `phone_bank`,
   `missing_poster`, `map_card` (dùng `insertgen.draw_*` của B; fallback tự vẽ đơn giản nếu import lỗi), `timeline`,
   `info_card`, `job_ad`, `rule_list`, `badge` (trả về thông tin neo ngực để compositor vẽ theo xương torso).
   `rule_card` mới theo thiết kế sổ tay (giữ chữ ký `render_rule_card`). Layer động (timestamp, chat pop) dùng
   `Layer` có hàm vẽ theo t.
2. `effects.py` (mới):
   ```python
   class ShotEffects:
       def __init__(self, names: list[str], transition: str, W: int, H: int, duration: float, seed: int, backend): ...
       def pre_chars(self, c, t) -> None      # (để trống v1)
       def post_chars(self, c, t) -> None     # rain, fog
       def post_grade(self, c, t) -> None     # cctv, flash, fade_white, fade_black, glow, transition-in
       def frame_transform(self, t) -> tuple[skia.Matrix | None, float]  # shake_light offset, blur_in sigma
       def char_color_filter(self) -> skia.ColorFilter | None            # cctv: khử bão hoà nhân vật
   ```
   Tên không biết → bỏ qua + cảnh báo. Ngẫu nhiên seed theo shot id.
3. `post.py`: thêm `cctv_matrix()`, `scanlines_image(W,H)`, `noise` tái dùng grain; giữ API cũ.
4. `compositor.py` (móc):
   - Khởi tạo `ShotEffects(shot.effects, shot.transition, ...)`.
   - `render_at`: áp `frame_transform` → vẽ nền → `pre_chars` → nhân vật (chọn ảnh theo `cis.view`, áp
     `char_color_filter`) → lớp near → `post_chars` → `vignette` → `post_grade` → overlays → grain.
   - `view == "back"`: nếu actor là focus của close/medium → đặt tiền cảnh trái, scale ×1.8, blur σ 10 (over-shoulder).
   - `cctv` grid 4: dựng 4 `LocationAsset` nhỏ (cells) bằng `load_location`; split: nửa phải không áp cctv.
   - `badge`: vẽ sau actor theo ma trận xương torso.
   - Gọi `puppetgen`/`insertgen` qua API công khai trên; không sửa file của A/B.
5. `film.py`: v1 chuyển cảnh = hiệu ứng vào đầu shot (không cần crossfade giữa 2 file); `shot_hash` thêm
   `effects`, `transition` (đã nằm trong dữ liệu shot nếu hash cả model).

**Kiểm thử:** `tests/render_test_overlays.py` — dựng 1 storyboard tạm dùng mọi overlay/effect mới trên nền
`placeholder` (không phụ thuộc A/B), lưu ảnh tĩnh → `logs/overlays/`; storyboard cũ (không có trường mới) render
y hệt trước (so hash ảnh tĩnh `tests/render_smoke.py --quick`).

---

## Thứ tự & phụ thuộc
- A, B, C chạy **song song**. Phụ thuộc chéo chỉ qua API ghi ở trên, luôn có fallback khi phía kia chưa xong:
  B → `puppetgen.render_hand/render_portrait` (A); C → `insertgen.draw_*` (B).
- Tích hợp sau cùng (ngoài 3 gói): `pipeline.step_assets` gọi `make_archetype`/`make_catalog_locations`/`make_insert`
  khi `CharacterDef.archetype` hoặc `LocationDef.asset_id` trỏ tới id catalog; `script/vocab.py` + `script/prompts.py`
  thêm biểu cảm/overlay/effect mới cho Gemini; `asset_library.assign` ưu tiên khớp `CharacterDef.tags`.

## Ma trận sở hữu file

| File | A | B | C |
|---|---|---|---|
| storytoon/render/puppetgen.py, rig.py, actions.py | ✔ | | |
| assets/characters/** (archetype mới), tools/make_archetype_characters.py, tests/render_test_puppets.py | ✔ | | |
| storytoon/render/locgen.py, insertgen.py, location.py | | ✔ | |
| assets/locations/** (8 mới), assets/inserts/** (mới), tools/make_catalog_locations.py, tests/render_test_locations.py | | ✔ | |
| storytoon/render/overlays.py, post.py, effects.py, compositor.py, film.py, tests/render_test_overlays.py | | | ✔ |
| storytoon/schema.py, asset_library.py, pipeline.py, script/*, assets/catalog/*, docs/STYLE_GUIDE.md | đóng băng | đóng băng | đóng băng |
