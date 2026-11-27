# StoryToon — Style Guide (Hướng dẫn phong cách hình ảnh)

Hợp đồng thiết kế cho **thư viện tài sản gốc, dùng lại được** (nhân vật / địa điểm / ảnh chèn / overlay / hiệu ứng)
cho phim kể chuyện kinh dị – bí ẩn dạng **2D cutout puppet** (rối cắt giấy vector phẳng).

> **Quy tắc bản quyền (bắt buộc).** Các khung hình tham khảo thuộc một kênh bên thứ ba. Ta chỉ học **phong cách**,
> **ngữ pháp cảnh quay** và **nguyên mẫu nhân vật chung chung**. KHÔNG sao chép nhân vật cụ thể 1:1, tên, thương hiệu
> cửa hàng, logo mặt trời/mặt cười, tên sản phẩm, chữ trên poster, bố cục pixel-đối-pixel; KHÔNG cắt/nhúng ảnh tham
> khảo vào tài sản. Mọi biển hiệu, huy hiệu, tên, số liệu đều là **bịa mới, chung chung, bối cảnh Việt Nam**
> (tạp hoá, cửa hàng tiện lợi 24h, xe ôm, bến xe buýt, nhà trọ, đường quê...).

Dữ liệu máy đọc đi kèm tài liệu này:
`assets/catalog/archetypes.json`, `locations.json`, `inserts.json`, `overlays.json`, `effects.json`.
Kế hoạch dựng: `docs/ASSET_PLAN.md`. Khung hình chuẩn: **3840×2160** (nền) / xuất 1920×1080; mọi số % dưới đây theo
chiều cao khung (H) hoặc chiều rộng (W).

---

## 1. Dựng hình nhân vật (Character construction / cấu trúc rối)

| Thành phần | Quy tắc |
|---|---|
| Tỉ lệ đầu:thân (head:body) | **Cận / bán thân**: đầu ≈ 1/3 phần thân trên nhìn thấy. **Toàn thân**: đầu ≈ 1/4.5 – 1/5 chiều cao (người lớn), 1/3.5 (trẻ em), 1/5.5 (dáng cao gầy, "bóng ma cao"). |
| Đầu (head) | To, hình **trứng / chữ nhật bo tròn**, rộng nhất ở gò má. Không viền da (outline-less). |
| Cổ (neck) | **Dài, mảnh, hình trụ**, 2 nét gân nhạt (neck lines). Người già: thêm 1–2 nếp nhăn ngang. |
| Thân (torso) | Hình thang/hộp bo tròn, thẳng, cứng. |
| Vai & tay áo (puffed sleeves) | Khối vai **phồng tròn** tách rời như mảnh cắt riêng (capsule), khớp vai/khuỷu thấy rõ. |
| Tay (arms) | Ống tròn cứng, buông thẳng; khuỷu có nếp gấp. |
| Bàn tay (hands) | Toàn cảnh: dạng **găng (mitten)**. Cận cảnh POV: tay to, ngón là các capsule nối khớp tròn kiểu "ma-nơ-canh gỗ", móng sáng hình chữ nhật bo tròn, nếp đốt ngón. |
| Chân (legs) | Rất dài, mảnh; giày khối đơn giản. |
| Bóng đổ | Elip tối mờ dưới chân (α 0.35). |

**Khuôn mặt (face)**

- **Mắt (eyes)**: chấm/oval **đen đặc** nhỏ + **1 chấm sáng trắng** (catch-light) góc trên.
- **Quầng mắt (eye-bags)**: vệt xám-tím / nâu nhạt dưới mắt (người làm ca đêm, mệt).
- **Mũi (nose)**: chấm/oval nhỏ, đậm hơn da ~12%.
- **Má hồng (cheek blush)**: 2 elip hồng mềm (α 0.45), người già/trẻ em đậm hơn.
- **Lông mày (brows)**: nét cong ngắn dày; nghiêng để diễn cảm.
- **Tai (ears)**: nửa tròn/chữ C với 1 nét trong.
- **Miệng (mouth)**: chủ yếu là **1 nét** (cười nhẹ, thẳng, trễ xuống, gợn sóng); khi nói/há là hình oval tối có lưỡi hồng.

**Tô màu (shading)** — flat vector, **không viền** trên da:
1. Màu nền phẳng (base).
2. **Một tông tối hơn** (base × 0.82) cho mặt khuất / nửa mặt.
3. **Gradient mềm** dọc mép (rim) 10–15% bề rộng phần.
4. Chỉ đường may/nếp áo dùng nét mảnh tối hơn (base × 0.62). Không bóng đổ cứng kiểu cel.
5. Tóc: khối đen phẳng + **1 cung highlight xám-xanh** ở đỉnh + 2–3 vạch nhỏ.

**Phân cấp chi tiết theo cỡ (LOD)**: nhân vật cao < 25% H → bỏ quầng mắt, má, highlight tóc; < 12% H → chỉ còn
khối màu + chấm mắt (dùng cho "extra", CCTV).

### 1.1 Màu da (skin tones)

| id | hex | dùng |
|---|---|---|
| skin_fair | `#f1d3bd` | da trắng, học sinh nữ |
| skin_peach | `#e9b994` | mặc định |
| skin_tan | `#c9926a` | thanh niên làm ngoài trời |
| skin_brown | `#a8774f` | tài xế, công nhân, người già lao động |
| skin_ghost | `#c9ccd6` | ma nước, xanh xám lạnh |
| skin_corpse | `#e4e2dc` | ma trắng bệch |

---

## 2. Bộ biểu cảm (Expression set) — công thức vẽ chính xác

Mỗi biểu cảm = tổ hợp các slot `eyes` / `brows` / `mouth` + lớp FX (`fx`). Puppet phải có đủ ảnh slot cho các
trạng thái dưới đây. Tên khớp `schema.Expression`.

| expression | Mắt (eyes) | Mày (brows) | Miệng (mouth, khi im) | FX |
|---|---|---|---|---|
| `neutral` | `open` chấm đen + highlight | `neutral` cong nhẹ | `flat` nét thẳng ngắn | – |
| `happy` (cười) | `happy` cung ∩ hoặc open | `neutral` nâng 5% | `smile` cung ∪, có thể hé răng trắng | má hồng đậm +20% |
| `sad` (buồn) | `open`, mí trên trễ | `sad` đầu trong nâng lên (/ \\ ngược) | `frown` cung ∩ nhỏ | – |
| `angry` (giận) | `half` nheo | `angry` chữ V, đầu trong hạ thấp | `shout` oval há lộ răng hoặc ∩ chặt | gân xanh `vein` (tuỳ chọn) |
| `scared` (sợ) | `wide` tròng trắng + đồng tử nhỏ | `sad` cao | `wavy_small` | 1 giọt mồ hôi |
| `evil` (nham hiểm) | `half` | `evil` 1 bên nhướn, 1 bên hạ | `grin` cười xếch 1 bên | bóng tối nửa mặt (tuỳ chọn) |
| `surprised` (ngạc nhiên) | `open` to 1.15× | `surprised` cao, cong | `o_small` chữ o nhỏ tối, trong đỏ | – |
| `nervous` (lo lắng) | `open` | `sad` lệch (1 bên cao) | `wavy` **nét gợn sóng ~~~** | 2–3 **vạch mồ hôi** xanh nhạt chéo trên tóc + 1 giọt mồ hôi bên thái dương |
| `shocked` (sốc) | `shock` = **vòng trắng to, đồng tử chấm đen rất nhỏ** | `surprised` rất cao | `wavy` hoặc `o_small` | giọt mồ hôi, tuỳ chọn tia sốc |
| `crying` (khóc) | `teary`: mắt bóng, viền đỏ, vũng nước xanh nhạt ở mí dưới; **mắt sưng** (quầng tím đậm) | `sad` | `sob` oval há nhỏ hoặc `wavy` | 2 **dòng nước mắt** xanh nhạt chảy dọc má, giọt rơi |
| `tired` (mệt/buồn ngủ) | `half` mí nặng | `neutral` hạ 5% | `flat` hoặc `o_small` | quầng mắt tím đậm ×1.6 |
| `smirk` (nhếch mép) | `half` | 1 bên nhướn | `smirk` nét cong lệch 1 khoé | – |

**Khẩu hình nói (talking mouth shapes)** — 9 hình kiểu Rhubarb, giữ nguyên `A..H,X`:
`A` khép (m/b/p) · `B` hé răng · `C` há vừa (e) · `D` há rộng (a) · `E` tròn vừa (o) · `F` chụm (u/w) ·
`G` răng chạm môi (f/v) · `H` lưỡi (l) · `X` nghỉ. Khi nói, khẩu hình ghi đè miệng của biểu cảm nhưng **mắt/mày/FX giữ nguyên**.
Biểu cảm có miệng nghỉ riêng: `nervous`/`shocked` → `wavy`, `crying` → `sob`, `smirk` → `smirk`.

### 2.1 FX trên mặt (sweat / tear / vein)
- **Giọt mồ hôi (sweat drop)**: giọt nước xanh xám `#a9c4dc`, viền sáng, cao 6% đầu, ở thái dương trên.
- **Vạch mồ hôi / căng thẳng (stress dashes)**: 2–3 vạch chéo ngắn `#b9d3e6` phía trên tóc.
- **Nước mắt (tears)**: vũng xanh nhạt `#cfe6f5` α0.8 ở mí dưới + dòng hẹp chạy xuống cằm; giọt rơi animate.
- **Gân giận (vein)**: dấu "#" cong 4 nhánh màu đỏ `#d0302a` góc trán.
- **Má đỏ ửng (flush)**: elip hồng đậm hơn + 3 vạch chéo.
- **Nước nhỏ giọt (ghost drip)**: giọt `#9fc3dd` rơi từ đuôi tóc/cằm/tay (ma nước).

---

## 3. Kiểu tóc (Hair types)

| id | mô tả |
|---|---|
| `spiky` | Chỏm 4–5 gai tam giác nhọn trên đỉnh, 1 lọn mái chéo che trán, hai bên cạo (mảng màu da nhạt hơn) |
| `short_side_part` | Ngắn rẽ ngôi gọn, highlight cung |
| `buzz` | Cắt sát, khối mỏng |
| `bald` | Trọc, đầu sáng bóng 1 điểm highlight; tuỳ chọn viền tóc bạc hai bên |
| `curly_short` | Xoăn tít: cụm bong bóng tròn, mỗi lọn 1 cung sáng (uốn kiểu "tóc uốn bà cô") |
| `afro_curly` | Xoăn bồng to quanh đầu |
| `long_straight` | Dài thẳng quá vai, ngôi giữa nhọn chữ V, 2 rèm hai bên mặt; sau lưng là 1 khối đen cao |
| `long_ponytail` | Dài buộc thấp, dây buộc màu |
| `bob_bangs` | Bob ngang cằm, mái cắt răng cưa/gợn, 2 lọn mảnh hai bên má |
| `long_over_face` | Dài phủ kín mặt tới hông, sợi dọc, đuôi tua rách (ma) |
| `bun` | Búi cao (cô, bà) |
| `grey_short` | Ngắn bạc |
| `cap_hidden` | Che dưới mũ lưỡi trai |
| `none_entity` | Đầu oval nhỏ không tóc (thực thể) |

## 4. Trang phục (Outfit types)
`polo_uniform` (áo polo đồng phục, cổ + nẹp màu tương phản, bảng tên trắng, huy hiệu tròn gốc của ta) ·
`hoodie` (hoodie kéo/không kéo khoá, 2 dây rút trắng, túi kangaroo) · `utility_jacket` (áo khoác kaki xanh rêu,
túi ngực nắp, đường may đứt nét) · `tee` · `shirt_button` (sơ mi trắng, túi ngực) · `school_uniform_f`
(sơ mi trắng cổ tròn/nhọn + chân váy xếp ly xanh than/đen) · `school_uniform_m` (sơ mi trắng + quần xanh than) ·
`office_blouse` · `floral_blouse` (áo hoa nhí 5 cánh) · `ao_ba_ba` · `ao_dai` · `red_traditional_dress` ·
`hi_vis_vest` (áo phản quang cam có số) · `police_uniform` · `security_uniform` · `nurse_scrubs` · `monk_robe`
(áo nâu/vàng nghệ) · `ritual_robe` (áo thầy cúng) · `pajamas` · `long_sheet_shirt` (áo xám rộng như tấm vải –
thực thể). Màu cụ thể: `assets/catalog/archetypes.json`.

**Huy hiệu đồng phục**: dùng **huy hiệu gốc** của thư viện — hình **chiếc lá trong vòng tròn** hoặc **ngôi sao 4 cánh**,
màu trắng trên nền đồng phục; tên cửa hàng hư cấu chung: "TẠP HOÁ 24H", "CỬA HÀNG TIỆN LỢI". Bảng tên dùng tên Việt
chung (An, Bình, Minh, Lan...) hoặc để trống.

## 5. Phụ kiện (Accessories)
Kính gọng đen chữ nhật · kính lão gọng vàng tròn + **dây đeo kính chấm chấm** · dây chuyền vàng + mặt dây chữ nhật ·
vòng ngọc xanh · dây chuyền bi bạc · tràng hạt (hạt tròn + tua đỏ) · mũ lưỡi trai · mũ bảo hiểm · balo · túi đeo chéo ·
kẹp/buộc tóc đỏ · bông tai giọt nước · bảng tên · huy hiệu · điện thoại · đèn pin · nhang.

---

## 6. Bảng màu (Palettes)

| palette | màu chính (hex) | ghi chú |
|---|---|---|
| `day` | trời `#9fb4c8`, cây `#7f9a6a`, đường `#8c8a86`, đất `#6e5a4a` | trời u ám xanh xám, ít bão hoà |
| `dusk` | trời `#3a3f7a`→`#8a6a9a`, mây `#d9a7b5`, đèn `#f2c46b` | tím chàm, mây hồng |
| `night` | trời `#141a2e`, núi `#0f1424`, đèn trong nhà `#fff6dc`, trăng `#f1ead2` | xanh navy sâu, chỉ khối sáng là điểm nhấn |
| `indoor` (cửa hàng, đèn huỳnh quang) | tường/sàn `#eef0f2`/`#d9dde2`, hàng hoá đỏ `#d8423a` cam `#f08a2c` vàng `#f3c94e` xanh lá `#4fa35a` lam `#3a78c2` hồng `#c74a9a` | trắng lạnh + khối màu bão hoà |
| `indoor_dim` (phòng nhân viên) | tường `#8e877c`, tủ `#4d6278`, bàn `#6b4a32`, đỏ `#b5332b` | ấm xám, vignette nặng |
| `cctv` | xám xanh đơn sắc `#9aa8a4`, tối `#2b3533` | khử bão hoà 85–100%, tint teal |
| `ghost` | da `#c9ccd6`, áo `#d8dbe0`, quầng `#7d8aa3` | khử bão hoà lạnh |
| `otherworld_frozen` | navy `#1f2a44`, băng `#e6f1f8`, đỏ bạc `#8a4a52` | thế giới "đóng băng" |
| `brand_store` (thương hiệu gốc) | xanh lục bảo `#1f6f5c`, kem `#f2ead8`, cam `#e8833a` | **khác hẳn** đỏ-vàng của tham khảo |

**Logic màu**: thế giới người sống ấm & bão hoà; ma lạnh, khử bão hoà; **đỏ** dành cho nguy hiểm (luật cấm, tag nổi bật,
váy ma). Ma áo đỏ là phần tử bão hoà duy nhất trong cảnh đã khử màu.

---

## 7. Quy tắc vẽ nền (Background rendering)

1. **Flat 2D** + gradient mềm; không nét viền; texture nhiễu nhẹ (noise 3–5%).
2. Phong cách **"low-poly 3D"** (cửa hàng, phòng) là tuỳ chọn: **xấp xỉ bằng mặt phẳng tô phẳng** — mỗi khối hộp có
   3 mặt: mặt trên sáng (base×1.12), mặt trước base, mặt bên base×0.78. Phối cảnh 1 điểm tụ (one-point perspective)
   cho hành lang/lối kệ; mặt đứng trực giao (orthographic facade) cho mặt tiền.
3. Lớp parallax: `far` (trời, núi) / `mid` (nhà, kệ) / `near` (tiền cảnh mờ: quầy, kệ sát camera).
4. Đèn: halo `screen` blend (đèn đường, trăng, cửa kính sáng), nón sáng hình thang α 0.18, vũng sáng elip trên mặt đất.
5. Kính: 2–3 **vệt phản chiếu chéo** trắng α 0.12–0.2.
6. Hàng hoá: hình chữ nhật màu bão hoà + nhãn sáng hơn bên trong; chai = chữ nhật bo + nắp vuông.
7. **Không có chữ do AI vẽ**. Mọi chữ (biển hiệu, nhãn kệ, poster) là lớp text thật (`signs`), tiếng Việt, NFC.
8. Mỗi địa điểm có **plate trống** (không người) để dùng lại trước/sau khi nhân vật "xuất hiện".

## 8. Blur / độ sâu trường ảnh (Depth of field)

| framing | blur nền (σ, theo px khung 1080p) | làm tối nền |
|---|---|---|
| wide | 0 | 0 |
| medium | 0–2 | 0 |
| close (bán thân, nhân vật 45–60% H, chính giữa) | **6–9** | −15% |
| extreme_close | 10–14 | −25% |
| insert trên nền "cảnh" | 14–20 | −35% |

- Tiền cảnh **qua vai (over-shoulder, `view: back`)**: đầu/vai nhân vật sau lưng phóng to 1.6–2×, đặt góc dưới trái,
  blur σ 8–12.
- **Blur toàn khung** dùng làm chuyển cảnh/nhịp thở (`transition: blur`, hiệu ứng `blur_in`).

---

## 9. Overlay (lớp đồ hoạ trên khung)

Tất cả overlay **không bị chỉnh màu** (vẽ sau grade), font **Be Vietnam Pro** (Bold/SemiBold), text NFC. Kích thước
theo % H trừ khi ghi khác. Tham số máy đọc: `assets/catalog/overlays.json`.

| kind | thiết kế |
|---|---|
| **subtitle** (phụ đề) | Giữa-dưới, baseline 88–90% H, trắng Bold bo tròn, cỡ 4.2–4.5% H, viền tối mảnh + bóng mềm, **không hộp**, 1 dòng, 2–6 từ/cụm, đổi nhanh theo câu. Luôn trên cùng (cả trên CCTV/split). |
| **nametag – floating** (`nametag`) | Thẻ ngà bo góc cạnh đầu nhân vật, chấm xanh lá trái, tên Bold + vai trò xám nhỏ; fade 0.3 s. |
| **badge – trên áo** (`badge`) | Bảng tên trắng nhỏ chữ nhật trên ngực trái áo đồng phục (chữ đỏ sẫm), vẽ như **một phần trang phục**, chạy theo xương torso; `data.text`, `data.color`. Dùng khi chỉ cần gợi tên, không cần thẻ nổi. |
| **location/time card** | Góc trên-trái, nền nâu-đỏ đậm viền nhạt, chấm đỏ (đã có). |
| **chapter_card** | Giữa khung, bảng tối viền vàng, tên phim lớn + số chương ô đỏ (đã có). Biến thể "chữ trên nền đen" cho nhịp kinh dị: chỉ text trắng giữa khung đen. |
| **rule_card** (thẻ luật – kiểu sổ tay) | Góc trên trái/phải, 30% W × 24% H, giấy kem kẻ dòng xanh, **thanh lề đỏ dày** bên trái + 1 đường lề đỏ mảnh, bo góc, bóng mềm. Trên: pill đen có chấm đỏ + tam giác cảnh báo vàng + "LUẬT N". Thân: 2 dòng chữ xanh đậm Bold 3.5% H, từ khoá đỏ. Dòng phụ xám, giãn chữ, IN HOA. Gạch dưới đỏ ngắn. Trượt/pop vào. |
| **rule_list** (tờ luật toàn khung) | Giấy vở kẻ (kem, dòng xanh nhạt, lề đỏ), dán băng keo be 2 góc trên, nghiêng −2°, giữa nền tối; tiêu đề xanh đậm lớn; N luật đánh số kiểu chữ viết tay xanh; 1 luật đỏ; tuỳ chọn **thanh bôi đen** che dòng cuối, vết cà phê, chữ in ngược thấm mặt sau. Tuỳ chọn 2 tay POV cầm mép dưới. Camera pan dọc chậm. Biến thể `blurred` (cố ý không đọc được). |
| **cctv** (HUD camera an ninh) | Trên-trái: chấm đỏ nhấp nháy + "REC" trắng Bold 3.3% H; dòng dưới "CAM n · nhãn" 2% H. Trên-phải: hộp đếm người (13–14% W × 12% H, đen 85%, viền sáng 1px, bo 8px): icon camera + chấm đỏ, nhãn "SỐ NGƯỜI TRONG CỬA HÀNG" nhỏ, **số trắng rất to** + đơn vị. Dưới-phải: timestamp `DD-MM-YYYY HH:MM:SS` xám sáng 3% H, giây chạy. **Lưới 4 (2×2)**: khe đen 4px, mỗi ô nhãn "CAM n" trên-trái + chú thích dưới-trái. **Split** "trên camera / bằng mắt thường": vạch giữa, pill nhãn mỗi nửa. Hộp đếm có thể phóng to ra giữa (×2.5) khi nền blur. |
| **phone_chat** | Điện thoại hiện đại (viền đen, notch dạng viên thuốc) giữa khung, có thể cầm bằng tay puppet; dark mode: thanh trạng thái (giờ, sóng, pin), header avatar tròn chữ cái đầu + tên + trạng thái, bong bóng xám (đến) / xanh (đi), thanh nhập "+" và nút gửi. Biến thể **màn khoá**: đồng hồ to, ngày, 1 thẻ thông báo (icon chat chung chung). Không dùng icon/brand thật. |
| **phone_bank** | Header gradient xanh dương với số dư lớn + tên TK (che số), danh sách giao dịch nền trắng: số âm đỏ, dương xanh. Ngân hàng hư cấu, không logo thật. |
| **missing_poster** (TÌM NGƯỜI MẤT TÍCH) | Tờ giấy dán băng keo 2 góc, dải đầu đỏ chữ trắng Bold, ảnh thẻ trong khung nhạt (hoặc ô trống/hình tròn cam), tên + tuổi Bold, dòng xám mô tả, dòng ngày giờ đỏ, SĐT che bớt số. Biến thể: rách mép, nhàu (nếp gấp), dán tường. |
| **map_card** | Thẻ giấy kem có sọc dọc mờ trên nền than khói; tiêu đề + phụ đề nhỏ góc trên-trái; đường xám có vạch giữa vàng + nhãn tên đường; kênh/sông xanh lượn sóng; **chấm đỏ + đường dẫn đứt + chú thích đỏ** "điểm xảy ra · 03:00"; pill xanh dưới-trái. |
| **timeline** | Nền navy tối toàn khung; tiêu đề giữa trên (Bold kem + phụ đề IN HOA xám); thanh tiến độ 6 gạch bo; hàng N **hình nhân không mặt** (tròn + hình thang, cổ áo vàng) trên đường đỏ; thẻ năm kem dưới mỗi hình; thẻ cuối đỏ chữ trắng (người hiện tại). Hiện dần từng hình. |
| **info_card** (thẻ thông tin/giá) | Giữa-trái, 31% W × 27% H, kem `#f3ede2` bo góc, thanh nhấn vàng 6px bên trái; pill đen "GIÁ · POS"; các dòng nhãn/giá trị, dòng cuối đỏ đậm; chân thẻ IN HOA xám. Phần còn lại khung blur. |
| **job_ad** (tin tuyển dụng) | Thẻ trắng nghiêng nhẹ, dải đầu vàng có icon + tên cửa hàng hư cấu + "24H"; tiêu đề Bold "TUYỂN NHÂN VIÊN CA ĐÊM", giờ "22:00 – 06:00", **pill đỏ** lương chữ trắng to, chú thích nhỏ; mẩu giấy/băng keo bay quanh. |
| **watermark** | Mờ góc trên-phải (đã có). |

---

## 10. Hiệu ứng (Effects) — tên khớp `Shot.effects` / `Shot.transition`

| effect | mô tả & tham số mặc định |
|---|---|
| `rain` | Vệt trắng chéo mảnh (α 0.25, góc 75–80°, 600 vệt/4K), hạt rơi; mây thấp + grain đậm hơn. |
| `fog` | 2–3 lớp sương gradient trôi ngang (tốc độ 20–40 px/s ở 4K), α 0.15–0.35, dày ở dưới/trong lối kệ, cửa tủ lạnh. |
| `cctv` | Khử bão hoà 90% + tint teal, scanline ngang (2px, α 0.08), noise 6%, méo fisheye nhẹ (k=0.08), vignette đậm, + HUD nếu có overlay `cctv`. |
| `flash` | Lóe trắng: α 0→0.9→0 trong 0.25 s (bật đèn, chụp ảnh, giật mình). |
| `fade_white` | Bloom phơi sáng quá → trắng ở cuối shot (0.6 s). Choáng/mất ý thức. |
| `fade_black` | Tối dần về đen ở cuối shot (0.5 s). |
| `blur_in` | Mở đầu shot blur σ 18 → 0 trong 0.8 s (tỉnh lại, hé lộ). |
| `glow` | Bloom quanh vùng sáng (đèn, trăng, cửa kính): ngưỡng 0.8, σ 12, cộng screen α 0.5. |
| `shake_light` | Rung nhẹ khung ±4 px @ 12 Hz (khác `camera: shake` mạnh). |

**Chuyển cảnh (`transition` – vào shot)**: `cut` (mặc định), `fade` (qua đen 0.4 s), `blur` (blur-out shot trước +
blur-in shot này 0.5 s), `white` (qua trắng 0.3 s).

**Hiệu ứng cục bộ** (gắn vào tài sản, không phải `Shot.effects`): vệt mồ hôi, nước mắt, nhỏ giọt, tia sốc trắng tỏa
quanh tay ma nắm cổ chân, vỡ băng (mảnh đa giác trong suốt), dấu tay mờ trên kính có vệt chảy, sóng âm hình cung
quanh chuông cửa, sao va chạm + chữ tượng thanh ("RẦM!"), gạch đỏ xoá tên (animate), sao đêm lấp lánh. Hậu kỳ
luôn bật: **vignette tròn mạnh** + **film grain mịn** (đã có trong `post.py`).

---

## 11. Ngữ pháp cảnh quay & thời lượng (Shot grammar & durations)

Phim kể chuyện, **1 cụm phụ đề / 1 shot**, cắt mỗi **1.5–4 s**. Camera gần như tĩnh: `push_in_slow`, pan chậm.
Nhân vật chỉ chớp mắt, đổi khẩu hình/biểu cảm, nhún nhẹ.

| # | loại shot | framing / bố cục | thời lượng điển hình |
|---|---|---|---|
| 1 | **Toàn cảnh thiết lập** (establishing) – cửa hàng đêm, bãi đất, đường quê | `wide`, nhân vật tí hon hoặc không, nhiều khoảng tối | 2.5–4 s, push chậm |
| 2 | **Bán thân nói chuyện** (talking head) | `close`, 1 nhân vật chính giữa, nhìn thẳng, ngực trở lên 45–60% H, nền blur tối | 1.5–3 s |
| 3 | **Hai người** (two-shot) | 2 bán thân cạnh nhau nhìn camera, **hoặc** 1 sau gáy tiền cảnh trái + 1 đối diện lệch phải | 2–3 s |
| 4 | **Ảnh chèn đạo cụ/tài liệu** (insert) | đồ vật chính giữa, đối xứng, nền tối vignette; tài liệu pan dọc chậm | 2–4 s |
| 5 | **POV tay** | tay to vào từ đáy khung: cầm giấy/điện thoại, nhón xu, bấm nút, bám mép quầy | 1.5–3 s |
| 6 | **Qua vai / sau lưng** (`view: back`) | nhân vật quay lưng đối diện mối đe doạ (cửa cuốn, cửa kính) | 2–3 s |
| 7 | **Hành lang 1 điểm tụ** | đối xứng, nhân vật tí hon ở điểm tụ | 2–4 s |
| 8 | **CCTV** | đơn / lưới 4 / split; ma chỉ thấy trên camera; số người 1→2 | 2–4 s mỗi cam |
| 9 | **Infographic** | timeline, bản đồ, thẻ giá | 3–5 s |
| 10 | **Khung đen chỉ phụ đề** | gradient tối, giữ câu | 1.5–2.5 s |

Chu kỳ điển hình: (1) → (2) → (4) → (6) → (2) → (8) → (4)… Giờ giấc truyền tải bằng **chèn đồng hồ** lặp ở các giờ khác
nhau / timestamp CCTV. Plate trống được chiếu trước khi nhân vật "pop" vào. Nhịp kinh dị: cắt sang đen chỉ còn phụ đề,
lóe trắng, hoặc blur.
