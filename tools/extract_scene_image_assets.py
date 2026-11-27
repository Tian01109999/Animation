"""Extract reviewed, reusable library entries from the supplied Sigma Lens still.

Only source pixels are used: no image generation, reconstruction, or hidden-pixel fill.
Character rigs are deliberately idle-only because this is a single rendered frame.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def cutout(image: Image.Image, polygon: list[tuple[int, int]], padding: int = 6) -> tuple[Image.Image, tuple[int, int, int, int]]:
    points = np.asarray(polygon, dtype=np.int32)
    x0 = max(0, int(points[:, 0].min()) - padding)
    y0 = max(0, int(points[:, 1].min()) - padding)
    x1 = min(image.width, int(points[:, 0].max()) + padding + 1)
    y1 = min(image.height, int(points[:, 1].max()) + padding + 1)
    points -= [x0, y0]
    rgb = np.asarray(image.crop((x0, y0, x1, y1)).convert('RGB')).copy()
    shape = (y1-y0, x1-x0)
    polygon_mask = np.zeros(shape, np.uint8)
    cv2.fillPoly(polygon_mask, [points], 255)
    expanded = cv2.dilate(polygon_mask, np.ones((5, 5), np.uint8))
    sure = cv2.erode(polygon_mask, np.ones((5, 5), np.uint8))
    labels = np.full(shape, cv2.GC_BGD, np.uint8)
    labels[expanded > 0] = cv2.GC_PR_FGD
    labels[sure > 0] = cv2.GC_FGD
    bg_model, fg_model = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), labels, None,
                bg_model, fg_model, 4, cv2.GC_INIT_WITH_MASK)
    alpha = np.where((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # GrabCut may absorb similarly colored refrigerator panels. The reviewed contour is
    # the hard outer limit, so no neighboring scene pixels can leak into the cutout.
    alpha = cv2.bitwise_and(alpha, polygon_mask)
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8), iterations=1)
    return Image.fromarray(np.dstack([rgb, alpha]), 'RGBA'), (x0, y0, x1, y1)


def fit_character(pixels: Image.Image, target_height: int = 1000) -> Image.Image:
    scale = target_height / pixels.height
    return pixels.resize((max(1, round(pixels.width*scale)), target_height), Image.Resampling.LANCZOS)


def save_static_character(folder: Path, image: Image.Image, *, label: str, name: str,
                          gender: str, age: str, tags: list[str], description: str,
                          coverage: str, head_bottom: int, source: Path, crop: tuple[int, ...],
                          capture_pose: str) -> None:
    folder.mkdir(parents=True, exist_ok=False)
    pixels = fit_character(image)
    width, height = pixels.size
    pixels.save(folder/'preview.png')
    pixels.save(folder/'character.png')
    # A single image part preserves the original pose/expression exactly. It cannot lip-sync.
    metadata = {
        'id': folder.name,
        'height_px': height,
        'image_scale': 1,
        'canvas': [width, height],
        'head_box': [width*.12, 0, width*.88, min(height, head_bottom)],
        'bones': {'root': {'parent': None, 'pivot': [width/2, height]}},
        'parts': [{'name': 'captured_frame', 'bone': 'root', 'offset': [0, 0],
                   'image': 'character.png', 'z': 0}],
        'expressions': {'neutral': {}},
        'profile': {
            'label': label, 'name_vi': name, 'gender': gender, 'age': age,
            'description': description, 'tags': tags, 'style': 'cutout',
            'coverage': coverage, 'actions': ['idle'], 'lipsync': False,
            'views': ['front'], 'capture_pose': capture_pose,
            'capture_quality': 'single-frame source; original resolution retained then scaled for the rig',
        },
        'provenance': {
            'kind': 'scene_image_extract', 'source': source.name,
            'crop_xyxy': list(crop), 'method': 'reviewed polygon + GrabCut from provided pixels',
            'generated': False, 'reviewed': True,
            'limitations': ['fixed captured pose and facial expression', 'no generated body parts',
                            'idle only; no lip-sync or back view'],
        },
    }
    write_json(folder/'character.json', metadata)


def save_insert(folder: Path, image: Image.Image, *, label: str, tags: list[str],
                props: list[str], kind: str, source: Path, crop: tuple[int, ...]) -> None:
    # The established insert catalog is flat: image + same-stem JSON in assets/inserts/.
    insert_id = folder.name
    folder = ROOT/'assets/inserts'
    folder.mkdir(parents=True, exist_ok=True)
    out = folder/f'{insert_id}.png'
    image.save(out)
    write_json(folder/f'{insert_id}.json', {
        'id': insert_id, 'label': label, 'label_en': label, 'tags': tags, 'props': props,
        'style': 'cutout', 'image': out.name, 'kind': kind,
        'camera_default': 'static', 'provenance': {
            'kind': 'scene_image_extract', 'source': source.name,
            'crop_xyxy': list(crop), 'method': 'crop of unobstructed source pixels',
            'generated': False, 'reviewed': True,
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    source = args.image.resolve(strict=True)
    frame = Image.open(source).convert('RGB')
    if frame.size != (1365, 768):
        raise SystemExit(f'Ảnh nguồn thay đổi kích thước: {frame.size}')

    # Clear counter/backsplash patch only: no people, subtitle, or watermark.
    location_id = 'bep_kho_lanh_quay_central_1300s'
    location_dir = ROOT/'assets/locations'/location_id
    if location_dir.exists():
        raise FileExistsError(location_dir)
    location_crop = (618, 299, 1085, 562)
    plate = frame.crop(location_crop).resize((1920, 1080), Image.Resampling.LANCZOS)
    location_dir.mkdir(parents=True)
    plate.save(location_dir/'bg.jpg', quality=95)
    write_json(location_dir/'location.json', {
        'id': location_id, 'name': 'Quầy bếp kho lạnh · góc chậu và bát',
        'size': [1920, 1080], 'time_of_day': 'indoor', 'bg': 'bg.jpg',
        'floor_y': 1020, 'char_px_per_unit': 0.30, 'signs': [],
        'profile': {
            'label': 'Quầy bếp kho lạnh · góc chậu và bát',
            'description': 'Một góc bếp công nghiệp cạnh kho lạnh; quầy inox, tường gạch men và hàng bát.',
            'kind': 'industrial_kitchen_counter_detail',
            'tags': ['bếp công nghiệp', 'kho lạnh', 'quầy inox', 'tường gạch men', 'bát',
                     'indoor', 'industrial kitchen', 'counter'],
            'style': 'cutout', 'layout': 'Ảnh crop trung cảnh từ scene; vùng tường và quầy sạch người.',
            'coverage': 'counter-detail-only',
        },
        'provenance': {
            'kind': 'scene_image_extract', 'source': source.name, 'source_path': str(source),
            'crop_xyxy': list(location_crop), 'method': 'clean background crop; resized without outpainting',
            'generated': False, 'reviewed': True,
            'limitations': ['counter-detail background, not a full-room/wide establishing view'],
        },
    })

    # Portrait: use only the older man's face/head; his tattooed arm overlaps another person.
    butcher_polygon = [(3, 417), (5, 405), (13, 393), (26, 385), (41, 383), (53, 389),
                       (62, 400), (66, 414), (65, 429), (62, 442), (56, 454), (46, 465),
                       (34, 471), (22, 470), (12, 465), (5, 454), (2, 439)]
    butcher_pixels, butcher_crop = cutout(frame, butcher_polygon, 4)
    save_static_character(
        ROOT/'assets/characters/nam_lon_tuoi_hoa_xam_mat_scene_1300s', butcher_pixels,
        label='Nam · lớn tuổi · tóc bạc ngắn · hình xăm mặt',
        name='Nam lớn tuổi tóc bạc ngắn, có hình xăm mặt', gender='male', age='old',
        tags=['old', 'grey_hair', 'bald', 'face tattoo', 'short grey hair'],
        description='Nam lớn tuổi, tóc thưa bạc ở hai bên, có vệt xăm trên mặt; ảnh chỉ gồm đầu và cổ.',
        coverage='portrait', head_bottom=1000, source=source, crop=butcher_crop,
        capture_pose='front-facing head portrait; facial markings are part of the captured frame',
    )

    # Full standing guard/staff figure; the hand-held dark object and open-mouth expression are baked in.
    guard_polygon = [(1098, 402), (1099, 396), (1103, 391), (1109, 391), (1112, 398),
                     (1114, 404), (1122, 405), (1133, 408), (1144, 412), (1148, 414),
                     (1153, 384), (1162, 368), (1173, 360), (1186, 359), (1195, 365),
                     (1199, 377), (1200, 392), (1197, 406), (1191, 418), (1187, 424),
                     (1191, 430), (1196, 443), (1198, 458), (1198, 471), (1193, 479),
                     (1192, 565), (1195, 576), (1198, 583), (1196, 589), (1172, 590),
                     (1167, 586), (1168, 576), (1168, 480), (1155, 478), (1148, 471),
                     (1144, 442), (1141, 434), (1129, 431), (1118, 427), (1110, 424),
                     (1101, 419), (1098, 413)]
    guard_pixels, guard_crop = cutout(frame, guard_polygon, 5)
    # split coordinate is relative to the segmentation crop, before scaling to rig height
    guard_head_bottom = round((428-guard_crop[1]) * 1000 / (guard_crop[3]-guard_crop[1]))
    save_static_character(
        ROOT/'assets/characters/nam_nguoi_lon_toc_den_ao_vest_giu_do_scene_1300s', guard_pixels,
        label='Nam · người lớn · tóc đen · vest xám · tay giơ',
        name='Nam người lớn mặc vest xám', gender='male', age='adult',
        tags=['adult', 'short_hair', 'dark gray suit', 'white shirt', 'red tie',
              'arm extended', 'holding small dark object'],
        description='Nam người lớn tóc đen ngắn, mặc vest xám, sơ mi sáng và cà vạt đỏ; đứng thẳng, một tay giơ ra cầm vật nhỏ màu sẫm không xác định.',
        coverage='full_body', head_bottom=guard_head_bottom, source=source, crop=guard_crop,
        capture_pose='standing, arm fully extended with an unidentified dark object; captured mouth is open',
    )

    # Detail inserts are source-only crops with clear, generic object labels.
    save_insert(ROOT/'assets/inserts/dao_bep_tren_gia_scene_1300s', frame.crop((274, 336, 450, 435)),
        label='Dao bếp trên giá treo', tags=['dao bếp', 'giá treo dao', 'kitchen knife', 'knife rack'],
        props=['dao_bep', 'knife_rack'], kind='kitchen_knife_rack_detail', source=source,
        crop=(274, 336, 450, 435))
    save_insert(ROOT/'assets/inserts/thung_go_tron_tren_quay_scene_1300s', frame.crop((516, 496, 666, 580)),
        label='Thùng tròn gỗ trên quầy', tags=['thùng gỗ', 'thùng tròn', 'quầy bếp', 'wooden barrel'],
        props=['thung_go', 'wooden_barrel'], kind='wooden_barrel_detail', source=source,
        crop=(516, 496, 666, 580))

    print('Extracted 2 static character assets, 1 clean counter background, and 2 object inserts.')
    print('No parts were generated. Person-on-table scene was omitted because it is heavily occluded.')


if __name__ == '__main__':
    main()
