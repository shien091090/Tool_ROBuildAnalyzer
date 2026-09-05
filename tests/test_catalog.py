import sqlite3
from pathlib import Path

import pytest

from app.core import catalog
from app.core.db_reader import DbReader
from importer import db

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_DB = _REPO_ROOT / "data" / "ro_items.db"


def _row(item_id, name, desc, equip_type="armor", slot_count=0, onstart=None, internal=None):
    return {"item_id": item_id, "internal_name": internal, "display_name": name, "description": desc,
            "slot_count": slot_count, "class_num": 0, "equip_type": equip_type, "stat_vector": None,
            "onstart_equip_src": onstart, "combi_ids": None}


_ROWS = [
    _row(1, "上段帽", "說明\n系列 : ^777777頭具^000000  防禦 : ^77777710^000000\n位置 : ^777777頭上^000000 重量 : ^77777710^000000\n裝備 : ^777777全職業^000000", slot_count=1),
    _row(2, "上中帽", "系列 : ^777777頭具^000000\n位置 : ^777777頭上/中^000000\n裝備 : ^777777盧恩騎士系列^000000"),
    _row(3, "影子鎧甲", "系列 : ^777777影子裝備^000000\n位置 : ^777777鎧甲^000000  重量 : ^7777770^000000\n裝備 : ^777777全職業^000000"),
    _row(4, "影子鎧甲箱子", "系列 : ^777777影子裝備^000000\n位置 : ^777777鎧甲^000000\n裝備 : ^777777全職業^000000", equip_type=None),
    _row(5, "服飾帽", "系列 : ^777777服飾裝備^000000 防禦 : ^7777770^000000\n位置 : ^777777頭上^000000\n裝備 : ^777777全職業^000000"),
    _row(6, "鎧甲卡", "MHP+1\n系列 : ^777777卡片^000000\n裝備 : ^777777鎧甲^000000", equip_type="card"),
    _row(7, "萬用卡", "系列 : ^777777卡片^000000\n裝備 : ^777777所有欄位皆可^000000", equip_type="card"),
    _row(8, "改良石(頭上)", "說明", equip_type="card", onstart="function()\nSubSpellDelay(1)\nend"),
    _row(9, "雙手劍", "系列 : ^777777雙手劍^000000\n裝備 : ^777777盧恩騎士系列^000000", equip_type="Mweapon", slot_count=2),
    _row(10, "短劍", "系列 : ^777777短劍^000000\n裝備 : ^777777盜賊系列^000000", equip_type="Mweapon"),
    _row(11, "右飾品", "系列 : ^777777飾品(右)^000000\n裝備 : ^777777全職業^000000"),
    _row(12, "通用飾品", "系列 : ^777777飾品^000000\n裝備 : ^777777全職業^000000"),
    _row(13, "壞資料服飾", "系列 : ^777777服飾裝備防禦^000000\n位置 : ^777777頭上重量^000000"),
    _row(14, "鎧甲", "系列 : ^777777鎧甲^000000\n裝備 : ^777777全職業^000000", slot_count=1),
    _row(15, None, "系列 : ^777777鎧甲^000000"),
    _row(16, "右飾品卡", "系列 : ^777777卡片^000000\n裝備 : ^777777飾品(右)^000000", equip_type="card"),
]


@pytest.fixture
def reader(tmp_path):
    path = str(tmp_path / "c.db")
    conn = sqlite3.connect(path)
    db.create(conn)
    db.insert_items(conn, _ROWS)
    db.set_meta(conn, "import_date", "2026-09-04")
    conn.commit()
    conn.close()
    r = DbReader(path)
    yield r
    r.close()


def test_strip_color_codes():
    assert catalog.strip_color_codes("^777777鎧甲^000000 x") == "鎧甲 x"
    assert catalog.strip_color_codes(None) == ""


@pytest.mark.parametrize("desc,series,positions,equip", [
    (_ROWS[0]["description"], "頭具", {"頭上"}, "全職業"),
    (_ROWS[1]["description"], "頭具", {"頭上", "頭中"}, "盧恩騎士系列"),
    ("位置 : ^777777頭上中下^000000\n系列 : ^777777服飾裝備^000000", "服飾裝備", {"頭上", "頭中", "頭下"}, None),
    (_ROWS[12]["description"], "服飾裝備", {"頭上"}, None),
    ("沒有尾段", None, set(), None),
    (None, None, set(), None),
])
def test_parse_description_fields(desc, series, positions, equip):
    assert catalog.parse_description_fields(desc) == (series, frozenset(positions), equip)


def _ids(entries):
    return sorted(e.item_id for e in entries)


def test_equipment_for_head_slots(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(cat.equipment_for_slot("head_top")) == [1, 2]
    assert _ids(cat.equipment_for_slot("head_mid")) == [2]
    assert _ids(cat.equipment_for_slot("head_low")) == []


def test_equipment_shadow_excludes_box_and_costume(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(cat.equipment_for_slot("shadow_armor")) == [3]
    assert _ids(cat.equipment_for_slot("costume_top")) == [5, 13]
    assert _ids(cat.equipment_for_slot("armor")) == [14]


def test_weapon_job_filter(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(cat.equipment_for_slot("weapon")) == [9, 10]
    assert _ids(cat.equipment_for_slot("weapon", job_id=4252)) == [9]
    assert _ids(cat.equipment_for_slot("weapon", job_id=4254)) == [10]
    assert _ids(cat.equipment_for_slot("head_top", job_id=4254)) == [1]


def test_accessory_sides(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(cat.equipment_for_slot("acc_r")) == [11, 12]
    assert _ids(cat.equipment_for_slot("acc_l")) == [12]


def test_cards_for_slot(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(cat.cards_for_slot("armor")) == [6, 7]
    assert _ids(cat.cards_for_slot("weapon")) == [7]
    assert _ids(cat.cards_for_slot("acc_r")) == [7, 16]
    assert _ids(cat.cards_for_slot("acc_l")) == [7]
    assert cat.cards_for_slot("shadow_armor") == []
    assert cat.cards_for_slot("costume_top") == []


def test_stones_for_costume_slot(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(cat.stones_for_slot("costume_top")) == [8]
    assert cat.stones_for_slot("costume_mid") == []
    assert cat.stones_for_slot("armor") == []


def test_search_get_and_unclassified(reader):
    cat = catalog.ItemCatalog.from_reader(reader)
    assert _ids(catalog.ItemCatalog.search(cat.equipment_for_slot("head_top"), "上中")) == [2]
    assert _ids(catalog.ItemCatalog.search(cat.equipment_for_slot("head_top"), "")) == [1, 2]
    assert cat.get(14).slot_count == 1
    assert cat.get(15) is None  # 無display_name者不進目錄
    assert cat.unclassified_count() == 0


@pytest.mark.skipif(not _REAL_DB.exists(), reason="需要真實匯入資料 data/ro_items.db")
def test_real_db_spot_checks():
    with DbReader(str(_REAL_DB)) as r:
        cat = catalog.ItemCatalog.from_reader(r)
    assert 450295 in {e.item_id for e in cat.equipment_for_slot("armor")}
    assert 600024 in {e.item_id for e in cat.equipment_for_slot("weapon", job_id=4252)}
    assert 600024 not in {e.item_id for e in cat.equipment_for_slot("weapon", job_id=4255)}
    assert 400227 in {e.item_id for e in cat.equipment_for_slot("head_top")}
    assert 4302 in {e.item_id for e in cat.cards_for_slot("armor")}
    assert 29053 in {e.item_id for e in cat.stones_for_slot("costume_top")}
    assert 24764 in {e.item_id for e in cat.equipment_for_slot("shadow_armor")}
