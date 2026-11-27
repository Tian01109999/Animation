"""Read-only visual library and per-story casting. Never creates visual content."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from . import paths


class MissingAssets(RuntimeError):
    pass


DEFAULT_ACTIONS = ['idle', 'talk', 'walk', 'sit', 'point', 'nod', 'shake_head', 'scared']
DEFAULT_EXPRESSIONS = ['neutral', 'happy', 'sad', 'angry', 'scared', 'evil', 'surprised']
AGE_VI = {'child': 'trẻ em', 'young': 'trẻ', 'adult': 'người lớn', 'old': 'lớn tuổi'}
GENDER_VI = {'male': 'Nam', 'female': 'Nữ'}


def _plain(text) -> str:
    """Lowercase, diacritics removed (đ→d), non-alphanumerics collapsed to single spaces."""
    text = unicodedata.normalize('NFKD', str(text).lower().replace('đ', 'd'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def _tokens(text):
    return set(_plain(text).split())


# Canonical trait → phrases (vi + en, matched diacritics-insensitively on whole words).
# The first Vietnamese phrase in VI_TRAIT is used for the short label.
SYNONYMS: dict[str, tuple[str, ...]] = {
    'glasses': ('kính', 'đeo kính', 'mắt kính', 'kính cận', 'glasses', 'spectacles', 'eyeglasses'),
    'cap': ('mũ', 'nón', 'mũ lưỡi trai', 'nón kết', 'kê pi', 'cap', 'hat', 'cap hidden', 'police cap'),
    'ghost': ('ma', 'hồn ma', 'con ma', 'oan hồn', 'vong', 'quỷ', 'ghost', 'spirit', 'phantom', 'haunt'),
    'entity': ('thực thể', 'quái vật', 'sinh vật', 'entity', 'creature', 'monster', 'faceless smile'),
    'silhouette': ('hình nhân', 'bóng người', 'không mặt', 'silhouette', 'infographic'),
    'curly': ('tóc xoăn', 'xoăn', 'tóc uốn', 'uốn xoăn', 'curly', 'afro', 'curly short', 'afro curly'),
    'bald': ('hói', 'hói đầu', 'trọc', 'đầu trọc', 'bald', 'shaved head'),
    'uniform': ('đồng phục', 'uniform', 'polo uniform'),
    'long_hair': ('tóc dài', 'long hair', 'long straight', 'long ponytail', 'long over face', 'long dark hair'),
    'short_hair': ('tóc ngắn', 'short hair', 'short side part', 'buzz', 'đầu đinh'),
    'bob_hair': ('tóc bob', 'bob', 'bob bangs', 'tóc ngang vai', 'mái bằng'),
    'bun': ('búi', 'tóc búi', 'búi tóc', 'bun'),
    'ponytail': ('đuôi ngựa', 'buộc tóc', 'cột tóc', 'ponytail', 'pigtails'),
    'spiky_hair': ('tóc dựng', 'tóc vuốt', 'spiky', 'spiky hair'),
    'grey_hair': ('tóc bạc', 'bạc trắng', 'grey hair', 'gray hair', 'white hair'),
    'hoodie': ('hoodie', 'áo nỉ', 'áo hoodie', 'áo có mũ'),
    'jacket': ('áo khoác', 'jacket', 'utility jacket', 'kaki', 'khaki'),
    'school_uniform': ('học sinh', 'nữ sinh', 'nam sinh', 'cấp 3', 'student', 'school', 'school uniform', 'schoolgirl', 'schoolboy'),
    'police': ('công an', 'cảnh sát', 'điều tra viên', 'police', 'cop', 'officer', 'detective', 'police uniform'),
    'security': ('bảo vệ', 'gác', 'tuần đêm', 'security', 'guard', 'security uniform', 'watchman'),
    'nurse': ('y tá', 'điều dưỡng', 'bệnh viện', 'nurse', 'nurse scrubs', 'hospital'),
    'monk': ('sư', 'sư thầy', 'nhà sư', 'thầy cúng', 'pháp sư', 'thầy pháp', 'monk', 'priest', 'shaman', 'exorcist', 'monk robe', 'robe'),
    'driver': ('tài xế', 'lái xe', 'xe ôm', 'shipper', 'driver', 'taxi', 'motorbike'),
    'office': ('văn phòng', 'công sở', 'nhân viên văn phòng', 'office', 'office blouse', 'lanyard', 'phóng viên', 'reporter'),
    'shop_owner': ('chủ tiệm', 'chủ quán', 'bà chủ', 'ông chủ', 'chủ nhà trọ', 'bán hàng', 'tạp hoá', 'shop owner', 'shopkeeper', 'landlady', 'vendor'),
    'night_shift': ('ca đêm', 'nhân viên ca đêm', 'cửa hàng tiện lợi', 'thu ngân', 'night shift', 'cashier', 'clerk', 'convenience store'),
    'wet': ('ướt', 'ướt sũng', 'chết đuối', 'đuối nước', 'ma nước', 'wet', 'drowned', 'water'),
    'pale': ('nhợt nhạt', 'trắng bệch', 'tái', 'xanh xao', 'pale'),
    'red_dress': ('áo đỏ', 'váy đỏ', 'áo dài đỏ', 'red dress', 'red ao dai'),
    'dress': ('váy', 'đầm', 'dress', 'pajamas', 'đồ ngủ'),
    'ao_ba_ba': ('áo bà ba', 'ao ba ba', 'quê', 'nông thôn', 'rural'),
    'beard': ('râu', 'râu dê', 'beard', 'goatee', 'white goatee'),
    'stubble': ('râu lún phún', 'râu ria', 'stubble'),
    'heavy': ('béo', 'mập', 'to béo', 'bụng phệ', 'heavy', 'fat', 'chubby'),
    'thin': ('gầy', 'ốm', 'mảnh khảnh', 'thin', 'slim', 'skinny'),
    'tall': ('cao', 'cao lớn', 'cao gầy', 'tall'),
    'scar': ('sẹo', 'vết sẹo', 'scar'),
    'gold_necklace': ('dây chuyền vàng', 'dây chuyền', 'gold chain', 'gold necklace', 'gold chain square pendant'),
    'backpack': ('balo', 'ba lô', 'cặp sách', 'backpack'),
    'tired': ('mệt mỏi', 'quầng thâm', 'thâm quầng', 'tired', 'eye bags'),
    'wrinkles': ('nếp nhăn', 'nhăn nheo', 'wrinkles'),
    'narrator': ('người kể', 'người kể chuyện', 'narrator', 'protagonist', 'nhân vật chính'),
    'workwear': ('công nhân', 'thợ', 'worker', 'workwear', 'towel on neck'),
    'face_hidden': ('che mặt', 'phủ mặt', 'tóc phủ mặt', 'face hidden'),
}
VI_TRAIT = {
    'glasses': 'kính', 'cap': 'đội mũ', 'curly': 'tóc xoăn', 'bald': 'hói', 'bob_hair': 'tóc bob',
    'long_hair': 'tóc dài', 'bun': 'tóc búi', 'grey_hair': 'tóc bạc', 'spiky_hair': 'tóc dựng',
    'short_hair': 'tóc ngắn', 'hoodie': 'hoodie', 'jacket': 'áo khoác', 'school_uniform': 'học sinh',
    'police': 'công an', 'security': 'bảo vệ', 'nurse': 'y tá', 'monk': 'thầy cúng/sư',
    'driver': 'xe ôm/tài xế', 'office': 'văn phòng', 'shop_owner': 'chủ tiệm', 'night_shift': 'nhân viên ca đêm',
    'red_dress': 'áo đỏ', 'ao_ba_ba': 'áo bà ba', 'dress': 'váy', 'heavy': 'béo', 'beard': 'râu',
    'stubble': 'râu lún phún', 'wet': 'ướt', 'entity': 'thực thể', 'silhouette': 'hình nhân', 'ghost': 'ma',
    'uniform': 'đồng phục', 'scar': 'sẹo', 'gold_necklace': 'dây chuyền vàng',
}
# label order: role/outfit first, then hair, then special
_LABEL_ORDER = ('police', 'security', 'nurse', 'monk', 'driver', 'night_shift', 'shop_owner', 'office',
                'school_uniform', 'silhouette', 'entity', 'curly', 'bald', 'bob_hair', 'grey_hair', 'long_hair',
                'bun', 'spiky_hair', 'glasses', 'cap', 'hoodie', 'jacket', 'red_dress', 'ao_ba_ba', 'dress',
                'heavy', 'beard', 'stubble', 'scar', 'gold_necklace', 'short_hair', 'uniform', 'wet')
# Traits a story must ask for before an asset carrying them is cast (they change who the character *is*).
_RESTRICTED = {'ghost': 14, 'entity': 30, 'silhouette': 40, 'wet': 6, 'face_hidden': 6}
def _accented(text) -> str:
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFC', str(text).lower()).replace('_', ' ')))


# (accented pattern, plain pattern) per phrase. Accented text is matched with its diacritics so that
# "má"/"mà" never read as "ma" (ghost) and "kinh dị" never reads as "kính"; text typed without any
# diacritics ("toc xoan", "kinh") falls back to the plain patterns.
_PATTERNS = {trait: [(' ' + _accented(p) + ' ', ' ' + _plain(p) + ' ') for p in phrases if _plain(p)]
             for trait, phrases in SYNONYMS.items()}


def traits(text) -> set[str]:
    """Canonical traits mentioned in free text (vi or en, with or without diacritics)."""
    found: set[str] = set()
    for segment in re.split(r'[,.;:|/()\[\]\n]+', str(text or '')):
        if not segment.strip():
            continue
        if segment.isascii():
            padded = ' ' + _plain(segment) + ' '
            found |= {t for t, pats in _PATTERNS.items() if any(plain in padded for _, plain in pats)}
        else:
            padded = ' ' + _accented(segment) + ' '
            found |= {t for t, pats in _PATTERNS.items()
                      if any((acc if not acc.isascii() else plain) in padded for acc, plain in pats)}
    return found


def _tag_traits(tags) -> set[str]:
    out = set()
    for tag in tags or []:
        plain = _plain(tag)
        out |= traits(tag)
        if plain.replace(' ', '_') in SYNONYMS:
            out.add(plain.replace(' ', '_'))
    return out


def character_label(profile: dict[str, Any], *, limit: int = 3) -> str:
    """Short vi label, e.g. 'Nữ · trẻ · tóc bob · ma'."""
    found = _tag_traits(profile.get('tags', [])) | traits(profile.get('outfit', '')) | traits(profile.get('hair_style', ''))
    parts = [GENDER_VI.get(profile.get('gender'), 'Nam'), AGE_VI.get(profile.get('age'), 'người lớn')]
    picked = [VI_TRAIT[t] for t in _LABEL_ORDER if t in found and t in VI_TRAIT][:limit]
    if 'ghost' in found and 'ma' not in picked:
        picked.append('ma')
    return ' · '.join(parts + picked)


def _character_entry(file: Path, meta: dict[str, Any]) -> dict[str, Any]:
    profile = dict(meta.get('profile') or {})
    params = meta.get('generator', {}).get('params', {})
    profile.setdefault('gender', params.get('gender', 'male'))
    profile.setdefault('age', params.get('age', 'adult'))
    profile.setdefault('hair_style', params.get('hair_style', ''))
    profile.setdefault('outfit', params.get('outfit_type', ''))
    profile.setdefault('tags', [])
    profile.setdefault('roles', [])
    profile.setdefault('style', 'cutout')
    profile.setdefault('coverage', 'full_body')
    profile.setdefault('actions', list(DEFAULT_ACTIONS))
    profile.setdefault('lipsync', True)
    profile['name'] = profile.get('name_vi') or profile.get('label') or file.parent.name
    profile.setdefault('label', character_label(profile))
    profile.setdefault('description', profile['name'])
    expressions = meta.get('expressions')
    profile['expressions'] = list(expressions) if isinstance(expressions, dict) and expressions else list(
        profile.get('expressions') or DEFAULT_EXPRESSIONS)
    views = meta.get('views') or profile.get('views') or ['front']
    profile['views'] = list(views)
    profile['has_back_view'] = 'back' in profile['views']
    # roles mention variants ("hồn ma y tá (biến thể pale)"), so they never add restricted traits
    role_traits = traits(' | '.join(profile['roles'])) - set(_RESTRICTED) - {'pale'}
    profile['traits'] = sorted(_tag_traits(profile['tags']) | traits(profile['description']) | role_traits
                               | traits(profile['outfit']) | traits(profile['hair_style']))
    entry = {'id': file.parent.name, **profile}
    image_files = [p['image'] for p in meta.get('parts', []) if 'image' in p]
    image_files += [p for item in meta.get('parts', []) for p in item.get('images', {}).values()]
    entry['ready'] = bool(image_files) and all((file.parent / p).is_file() for p in image_files)
    preview = file.parent / 'preview.png'
    entry['preview'] = str(preview if preview.exists() else file.parent / (image_files[0] if image_files else 'preview.png'))
    entry['provenance'] = meta.get('provenance', {'kind': 'existing_library'})
    return entry


def catalog(root: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    root = root or paths.ASSETS
    result = {'characters': [], 'locations': [], 'inserts': []}
    for file in sorted((root / 'characters').glob('*/character.json')):
        try:
            result['characters'].append(_character_entry(file, json.loads(file.read_text(encoding='utf-8'))))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    for file in sorted((root / 'locations').glob('*/location.json')):
        try:
            meta = json.loads(file.read_text(encoding='utf-8'))
            profile = dict(meta.get('profile') or {})
            profile.setdefault('label', meta.get('name', file.parent.name))
            profile.setdefault('description', profile['label'])
            profile.setdefault('tags', [])
            profile['time_of_day'] = meta.get('time_of_day', 'indoor')
            profile.setdefault('style', 'cutout')
            bg = file.parent / meta.get('bg', 'bg.png')
            result['locations'].append({'id': file.parent.name, **profile, 'ready': bg.is_file(), 'preview': str(bg),
                                        'provenance': meta.get('provenance', {'kind': 'existing_library'})})
        except (OSError, ValueError, TypeError, KeyError):
            continue
    for file in sorted((root / 'inserts').glob('*')):
        if file.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            continue
        meta = {}
        try:
            meta = json.loads(file.with_suffix('.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        result['inserts'].append({'id': file.stem, 'label': meta.get('label', file.stem),
          'description': ', '.join(meta.get('tags', [])), 'tags': list(meta.get('tags', [])),
          'style': meta.get('style', 'cutout'), 'props': meta.get('props', []), 'kind': meta.get('kind'),
          'ready': True, 'preview': str(file), 'provenance': meta.get('provenance', {'kind': 'existing_library'})})
    return result


def prompt_catalog() -> str:
    data = catalog()
    chars = [{'id': e['id'], 'label': e['label'], 'name': e.get('name'), 'gender': e['gender'], 'age': e['age'],
              'traits': e.get('traits', []), 'roles': e.get('roles', [])[:4], 'coverage': e.get('coverage'),
              'actions': e.get('actions', []), 'lipsync': e.get('lipsync', False),
              'capture_pose': e.get('capture_pose'),
              'back_view': e.get('has_back_view', False)} for e in data['characters'] if e['ready']]
    locs = [{'id': e['id'], 'label': e['label'], 'time_of_day': e.get('time_of_day'), 'kind': e.get('kind'),
             'tags': e.get('tags', [])[:8]} for e in data['locations'] if e['ready']]
    inserts = [{'id': e['id'], 'label': e['label'], 'tags': e.get('tags', [])[:8], 'props': e.get('props', [])}
               for e in data['inserts'] if e['ready']]
    style = 'cutout'
    return (f"ASSET LIBRARY (the ONLY visuals that exist; the app never draws new images). Storyboard.style={style!r}.\n"
      'CHARACTERS: ' + json.dumps(chars, ensure_ascii=False) + '\n'
      'LOCATIONS: ' + json.dumps(locs, ensure_ascii=False) + '\n'
      'INSERTS (use as Shot.location="insert:<id>"): ' + json.dumps(inserts, ensure_ascii=False) + '\n'
      'CASTING RULES / QUY TẮC CHỌN DIỄN VIÊN:\n'
      '- Mỗi CharacterDef giữ id/tên/vai của câu chuyện; asset_id = id trong CHARACTERS khớp gender, age '
      '(child/old phải khớp chính xác; young/adult có thể thay nhau) và nhiều traits nhất (kính=glasses, '
      'mũ=cap, tóc xoăn=curly, hói=bald, đồng phục=uniform, ma=ghost...). Ghi các trait đó vào CharacterDef.tags.\n'
      '- KHÔNG gán cùng một asset_id cho hai nhân vật khác nhau khi còn asset phù hợp khác.\n'
      '- Asset có trait ghost/entity/silhouette chỉ dùng cho ma / thực thể / hình nhân infographic.\n'
      '- view="back" chỉ dùng với asset back_view=true. Nhân vật portrait chỉ medium/close/extreme_close.\n'
      '- Mỗi LocationDef chọn asset_id từ LOCATIONS theo mô tả + time_of_day; insert chỉ dùng id có trong INSERTS.\n'
      '- prop luôn null (chưa có đạo cụ cầm tay được rig). Không có asset phù hợp → asset_id=null; '
      'không bịa id, không yêu cầu tạo ảnh.')


def ai_assign(sb):
    from . import chatgpt
    response = chatgpt.generate([{'role': 'user', 'parts': [{'text':
        'Giữ nguyên id/tên/vai, lời thoại và thứ tự tất cả các cảnh. Chỉ chọn asset_id thích hợp '
        'cho từng nhân vật và địa điểm từ kho có sẵn theo giới tính, độ tuổi và ngoại hình (traits). '
        'Không gán trùng một asset cho hai nhân vật. Trả lại storyboard với bản gán. '
        'Không thay đổi nội dung câu chuyện.\n' + sb.model_dump_json()}]}])
    data = json.loads(response)
    char_map = {c.get('id'): c.get('asset_id') for c in data.get('characters', [])}
    loc_map = {loc.get('id'): loc.get('asset_id') for loc in data.get('locations', [])}
    # Only copy casting decisions. Never replace narrative text with an AI rewrite.
    for character in sb.characters:
        character.asset_id = char_map.get(character.id, character.asset_id)
    for location in sb.locations:
        location.asset_id = loc_map.get(location.id, location.asset_id)


def _compatible(character, entry, actions):
    if not entry.get('ready') or entry.get('gender') != character.gender:
        return False
    actual, requested = entry.get('age', 'adult'), character.age
    # child and old are strict; young/adult may stand in for each other
    if actual != requested and not ({actual, requested} <= {'young', 'adult'}):
        return False
    return set(actions) <= set(entry.get('actions', ['idle', 'talk']))


def wanted_traits(character) -> set[str]:
    text = ' | '.join([character.description or '', character.role or '', character.name or ''])
    return traits(text) | _tag_traits(getattr(character, 'tags', []) or [])


def score_character(character, entry, actions=(), wanted: set[str] | None = None) -> float:
    """Higher = better fit. Exposed for UI/tests."""
    wanted = wanted_traits(character) if wanted is None else wanted
    have = set(entry.get('traits', []))
    score = 5.0 * len(wanted & have)
    score += 8 if entry.get('age') == character.age else 0
    spirit = {'ghost', 'entity'}
    if wanted & spirit:
        # a story ghost may be played by any ghost/entity asset, but not by an ordinary human
        score += 6 if have & spirit else -10
    for trait, penalty in _RESTRICTED.items():
        if trait in spirit and wanted & spirit:
            continue
        if trait in have and trait not in wanted:
            score -= penalty
        if trait in wanted and trait not in have:
            score -= penalty / 2
    if getattr(character, 'archetype', None) and character.archetype in (entry['id'], entry.get('archetype')):
        score += 20
    if entry.get('lipsync') and 'talk' in actions:
        score += 2
    # light tie-break on loose word overlap (descriptions/roles)
    query = _tokens(character.description + ' ' + character.role)
    score += 0.5 * len(query & _tokens(entry.get('description', '') + ' ' + ' '.join(entry.get('roles', []))))
    return score


def assign(sb, *, root: Path | None = None) -> list[str]:
    """Validate AI selections and fill omitted selections from compatible existing assets."""
    data = catalog(root)
    notes = []
    style = 'stick' if 'stick' in sb.style.lower() else 'cutout'
    used: dict[str, str] = {}
    views_needed = {}
    for shot in sb.shots:
        for c in shot.characters:
            if c.view == 'back':
                views_needed[c.id] = True
    for character in sb.characters:
        actions = {c.action for shot in sb.shots for c in shot.characters if c.id == character.id}
        if not actions:
            continue
        candidates = [e for e in data['characters'] if _compatible(character, e, actions) and e.get('style') == style]
        if views_needed.get(character.id):
            candidates = [e for e in candidates if e.get('has_back_view')] or candidates
        fresh = [e for e in candidates if e['id'] not in used]
        selected = next((e for e in candidates if e['id'] == character.asset_id), None)
        if selected is not None and selected['id'] in used and fresh:
            notes.append(f"{character.name}: asset {selected['label']} đã dùng cho {used[selected['id']]}, chọn asset khác.")
            selected = None
        if selected is None and candidates:
            wanted = wanted_traits(character)
            pool = fresh or candidates
            selected = max(pool, key=lambda e: score_character(character, e, actions, wanted))
        character.asset_id = selected['id'] if selected else None
        if selected:
            used.setdefault(selected['id'], character.name)
            if not character.tags:
                character.tags = sorted(wanted_traits(character) & set(selected.get('traits', [])))
            notes.append(f"{character.name} → {selected['label']}")
    used_locations = {shot.location for shot in sb.shots}
    for location in sb.locations:
        if location.id not in used_locations:
            continue
        candidates = [e for e in data['locations'] if e['ready'] and e.get('style') == style]
        selected = next((e for e in candidates if e['id'] == location.asset_id), None)
        if selected is None:
            selected = next((e for e in candidates if e['id'] == location.id), None)
        if selected is None and candidates:
            query = _tokens(location.description + ' ' + location.name)
            def score_location(e):
                terms = _tokens(e.get('description', '') + ' ' + e['label'] + ' ' + ' '.join(e.get('tags', []))
                                + ' ' + str(e.get('kind', '')))
                label = _tokens(e['label']) or {''}
                precision = len(query & label) / len(label)   # prefer the plainest matching variant
                return (len(query & terms) * 4 + 6 * precision
                        + (3 if e.get('time_of_day') == location.time_of_day else 0))
            selected = max(candidates, key=score_location)
        location.asset_id = selected['id'] if selected else None
        if selected:
            notes.append(f"{location.name} → {selected['label']}")
    by_id = {c.id: c for c in sb.characters}
    entries = {e['id']: e for e in data['characters']}
    for shot in sb.shots:
        props = {c.prop for c in shot.characters if c.prop}
        cutaway = next((e for e in data['inserts'] if props and props <= set(e.get('props', []))
                        and e.get('style') == style), None)
        if cutaway:
            shot.location = 'insert:' + cutaway['id']
            shot.characters = []
            shot.framing = 'close'
            shot.focus = None
            notes.append(f"{shot.id}: dùng ảnh chèn {cutaway['label']} cho đạo cụ; giữ nguyên lời thoại.")
        if shot.framing == 'wide' and any(entries.get(by_id[c.id].asset_id, {}).get('coverage') == 'portrait'
                                         for c in shot.characters if c.id in by_id):
            shot.framing = 'medium'
            notes.append(f'{shot.id}: dùng trung cảnh để không lộ phần ngoài chân dung có sẵn.')
        for c in shot.characters:
            entry = entries.get(by_id[c.id].asset_id) if c.id in by_id else None
            if c.view == 'back' and entry and not entry.get('has_back_view'):
                c.view = 'front'
                notes.append(f'{shot.id}: {c.id} chưa có góc sau lưng trong kho, dùng góc trước.')
    return notes


def validate(sb, *, root: Path | None = None):
    data = catalog(root)
    style = 'stick' if 'stick' in sb.style.lower() else 'cutout'
    characters = {e['id']: e for e in data['characters']}
    locations = {e['id']: e for e in data['locations']}
    inserts = {e['id']: e for e in data['inserts']}
    problems = []
    for shot in sb.shots:
        if shot.location.startswith('insert:'):
            if shot.location[7:] not in inserts or inserts[shot.location[7:]].get('style') != style:
                problems.append(f'{shot.id}: thiếu ảnh chèn {shot.location[7:]}')
        else:
            definition = sb.location(shot.location)
            entry = locations.get(definition.asset_id if definition else shot.location)
            if not entry or not entry.get('ready') or entry.get('style') != style:
                problems.append(f'{shot.id}: chưa gán nền có sẵn cho {shot.location}')
        for c in shot.characters:
            definition = sb.character(c.id)
            entry = characters.get(definition.asset_id if definition else None)
            if not definition or not entry or not _compatible(definition, entry, {c.action}) or entry.get('style') != style:
                problems.append(f'{shot.id}: chưa có nhân vật phù hợp cho {c.id} ({c.action})')
            elif shot.framing == 'wide' and entry.get('coverage') == 'portrait':
                problems.append(f'{shot.id}: {c.id} chỉ có chân dung, cần chọn trung/cận cảnh')
            if c.prop:
                problems.append(f'{shot.id}: đạo cụ cầm tay {c.prop} chưa có trong kho')
    if problems:
        raise MissingAssets('Kho assets chưa đáp ứng: ' + '; '.join(dict.fromkeys(problems)) +
                            '. Chọn lại trong tab Kho assets hoặc bổ sung assets từ video; app không tạo phần thiếu.')


def filter_entries(entries, *, query: str = '', gender: str | None = None, age: str | None = None,
                   tags=(), back_view: bool = False):
    """UI filter: free-text (vi/en, diacritics-insensitive, synonym aware) + gender/age/trait facets."""
    want_traits = traits(query)
    tokens = _tokens(query)
    out = []
    for e in entries:
        if not e.get('ready'):
            continue
        if gender and e.get('gender') not in (None, gender):
            continue
        if age and e.get('age') not in (None, age):
            continue
        have = set(e.get('traits', [])) | set(e.get('tags', []))
        if tags and not set(tags) <= have:
            continue
        if back_view and not e.get('has_back_view'):
            continue
        if tokens:
            hay = _tokens(' '.join([e.get('label', ''), e.get('name', '') or '', e.get('description', ''),
                                    ' '.join(e.get('tags', [])), ' '.join(e.get('roles', [])),
                                    ' '.join(e.get('traits', [])), str(e.get('gender', '')), str(e.get('age', ''))]))
            if not (tokens <= hay or (want_traits and want_traits <= set(e.get('traits', [])))):
                continue
        out.append(e)
    return out


def caption(entry) -> str:
    """Gallery caption with capability badges."""
    bits = [entry.get('label', entry['id'])]
    if entry.get('name') and entry.get('name') != entry.get('label'):
        bits.append(entry['name'])
    if 'expressions' in entry:
        bits.append(f"{len(entry['expressions'])} biểu cảm")
    if entry.get('has_back_view'):
        bits.append('có góc sau lưng')
    if entry.get('coverage') == 'portrait':
        bits.append('chân dung')
    return ' · '.join(bits)


def gallery_items(kind='characters'):
    return [(e['preview'], caption(e)) for e in catalog().get(kind, []) if e['ready']]
