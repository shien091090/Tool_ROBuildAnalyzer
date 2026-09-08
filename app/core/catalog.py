import re
from dataclasses import dataclass
from typing import Iterable

from app.core import jobs
from app.core.db_reader import DbReader

_RE_COLOR = re.compile(r"\^[0-9A-Fa-f]{6}")
_RE_SERIES = re.compile(r"系列\s*:\s*(\S+)")
_RE_POSITION = re.compile(r"位置\s*:\s*(\S+)")
_RE_EQUIP = re.compile(r"裝備\s*:\s*([^\n]+)")
_SERIES_JUNK = ("防禦:", "防具:", "防禦", "防具", ":")   # 壞資料黏字, 依序剝掉
_POSITION_JUNK = ("重量:", "重量", ":")


def strip_color_codes(text):
    return _RE_COLOR.sub("", text or "")


def _strip_junk(value, junk):
    for j in junk:
        if value.endswith(j):
            value = value[: -len(j)]
    return value


def _expand_positions(raw):
    raw = _strip_junk(raw, _POSITION_JUNK)
    if not raw:
        return frozenset()
    if raw.startswith("頭"):
        body = raw[1:].replace("/", "")
        return frozenset(f"頭{c}" for c in ("上", "中", "下") if c in body)
    return frozenset({raw})


_COSTUME_NAME_TAG = "(服飾)"
_COSTUME_SERIES = "服飾裝備"
_SERIES_AS_POSITION = frozenset({"披肩"})   # 服飾披肩常把系列寫成披肩且不寫位置, 拿系列補位置


def apply_costume_name_override(display_name, series, positions):
    """名稱帶「(服飾)」的道具一律視為服飾系列(client敘述有幾十件把系列誤寫成頭具/披肩,
    或整段漏寫), 敘述的系列欄只拿來補位置; 名稱沒帶就原樣回傳。"""
    if _COSTUME_NAME_TAG not in (display_name or ""):
        return series, positions
    if not positions and series in _SERIES_AS_POSITION:
        positions = frozenset({series})
    return _COSTUME_SERIES, positions


def parse_description_fields(description):
    text = strip_color_codes(description)
    if not text:
        return None, frozenset(), None
    m = _RE_SERIES.search(text)
    series = _strip_junk(m.group(1), _SERIES_JUNK) if m else None
    m = _RE_POSITION.search(text)
    positions = _expand_positions(m.group(1)) if m else frozenset()
    m = _RE_EQUIP.search(text)
    equip_text = m.group(1).strip() if m else None
    return (series or None), positions, equip_text


@dataclass(frozen=True)
class CatalogEntry:
    item_id: int
    internal_name: str | None
    display_name: str
    description: str
    slot_count: int
    equip_type: str | None
    has_onstart: bool
    series: str | None
    positions: frozenset[str]
    equip_text: str | None


_HEAD = frozenset({"頭具", "頭盔"})
_SHADOW = frozenset({"影子裝備"})
_COSTUME = frozenset({"服飾裝備", "服飾"})
# slot_key -> (允許系列, 必須位置或None); weapon另處理
_EQUIP_RULES: dict[str, tuple[frozenset[str], frozenset[str] | None]] = {
    "head_top": (_HEAD, frozenset({"頭上"})), "head_mid": (_HEAD, frozenset({"頭中"})), "head_low": (_HEAD, frozenset({"頭下"})),
    "armor": (frozenset({"鎧甲"}), None), "shield": (frozenset({"盾牌"}), None), "garment": (frozenset({"披肩"}), None),
    "shoes": (frozenset({"靴子", "鞋子"}), None),
    "acc_r": (frozenset({"飾品", "飾品(右)"}), None), "acc_l": (frozenset({"飾品", "飾品(左)"}), None),
    "shadow_armor": (_SHADOW, frozenset({"鎧甲"})), "shadow_gauntlet": (_SHADOW, frozenset({"手套"})),
    "shadow_shield": (_SHADOW, frozenset({"盾牌"})), "shadow_shoes": (_SHADOW, frozenset({"靴子", "鞋子"})),
    "shadow_earring": (_SHADOW, frozenset({"耳環"})), "shadow_pendant": (_SHADOW, frozenset({"墜子"})),
    "costume_top": (_COSTUME, frozenset({"頭上"})), "costume_mid": (_COSTUME, frozenset({"頭中"})),
    "costume_low": (_COSTUME, frozenset({"頭下"})), "costume_garment": (_COSTUME, frozenset({"披肩"})),
}
_WEAPON_TYPES = frozenset({"Mweapon", "Rweapon"})
# 卡片「裝備 : 」文字 → 可插槽位; 「所有欄位皆可」全部可插
_CARD_RULES: dict[str, tuple[str, ...]] = {
    "head_top": ("頭具",), "head_mid": ("頭具",), "head_low": ("頭具",), "armor": ("鎧甲",), "weapon": ("武器",),
    "shield": ("盾牌",), "garment": ("披肩",), "shoes": ("靴子", "鞋子"), "acc_r": ("飾品",), "acc_l": ("飾品",),
}
_CARD_SIDE_EXCLUDE = {"acc_r": "(左)", "acc_l": "(右)"}
_STONE_SUFFIX = {"costume_top": "(頭上)", "costume_mid": "(頭中)", "costume_low": "(頭下)", "costume_garment": "(披肩)"}


class ItemCatalog:
    def __init__(self, entries: Iterable[CatalogEntry]):
        self._by_id = {e.item_id: e for e in entries}
        self._by_name = sorted(self._by_id.values(), key=lambda e: e.display_name)

    @classmethod
    def from_reader(cls, reader: DbReader) -> "ItemCatalog":
        entries = []
        for item_id, internal, display, desc, slot_count, equip_type, has_onstart in reader.iter_catalog_rows():
            if not display:
                continue
            series, positions, equip_text = parse_description_fields(desc)
            series, positions = apply_costume_name_override(display, series, positions)
            entries.append(CatalogEntry(item_id, internal, display, desc or "", slot_count or 0, equip_type,
                                        has_onstart, series, positions, equip_text))
        return cls(entries)

    def get(self, item_id):
        return self._by_id.get(item_id)

    @staticmethod
    def _is_weapon(e):
        return e.equip_type in _WEAPON_TYPES

    @staticmethod
    def _equip_matches(e, slot_key):
        rule = _EQUIP_RULES.get(slot_key)
        if rule is None or e.equip_type != "armor":
            return False
        series_ok, positions_req = rule
        if e.series not in series_ok:
            return False
        return positions_req is None or bool(e.positions & positions_req)

    def equipment_for_slot(self, slot_key, job_id=None):
        if slot_key == "weapon":
            out = [e for e in self._by_name if self._is_weapon(e)]
        else:
            out = [e for e in self._by_name if self._equip_matches(e, slot_key)]
        if job_id is not None:
            out = [e for e in out if jobs.is_equippable_by(job_id, e.equip_text)]
        return out

    def cards_for_slot(self, slot_key):
        rule = _CARD_RULES.get(slot_key)
        if rule is None:
            return []
        exclude = _CARD_SIDE_EXCLUDE.get(slot_key)
        out = []
        for e in self._by_name:
            if e.equip_type != "card" or e.series != "卡片" or not e.equip_text:
                continue
            if "所有欄位皆可" in e.equip_text:
                out.append(e)
                continue
            if any(k in e.equip_text for k in rule) and not (exclude and exclude in e.equip_text):
                out.append(e)
        return out

    def stones_for_slot(self, slot_key):
        suffix = _STONE_SUFFIX.get(slot_key)
        if suffix is None:
            return []
        return [e for e in self._by_name
                if e.equip_type == "card" and e.has_onstart and e.display_name.endswith(suffix)]

    def unclassified_count(self) -> int:
        count = 0
        for e in self._by_name:
            if e.equip_type == "armor" and not any(self._equip_matches(e, k) for k in _EQUIP_RULES):
                count += 1
        return count

    @staticmethod
    def search(entries, query):
        q = (query or "").strip()
        return list(entries) if not q else [e for e in entries if q in e.display_name]
