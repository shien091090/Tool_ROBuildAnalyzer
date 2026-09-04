import json
import sqlite3
from importer import db


def _conn():
    c = sqlite3.connect(":memory:")
    db.create(c)
    return c


def test_create_builds_five_tables():
    c = _conn()
    names = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"items", "combos", "enchant_tables", "import_meta", "skills"} <= names


def test_create_builds_query_indexes():
    # Task 7 DB索引: enchant_tables(table_index, slot_index)與items(internal_name)
    # 查詢索引。idx_enchant_table_slot只有 DbReader.enchant_rows(WHERE
    # table_index=? ORDER BY slot_index DESC)真的用得到 — enchant_table_for_item
    # 是 SELECT DISTINCT ... FROM enchant_tables(無WHERE)的全表掃描, 不吃這個索引,
    # 該函式的效能瓶頸是Python端逐列json.loads(見db_reader.py docstring)。
    # idx_items_internal對應 DbReader.item_by_internal_name 的 WHERE internal_name=?。
    c = _conn()
    names = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_enchant_table_slot", "idx_items_internal"} <= names


def test_insert_items_roundtrip_json_fields():
    c = _conn()
    db.insert_items(c, [{
        "item_id": 450263, "internal_name": "Lunar_E_Armor_LT",
        "display_name": "月全蝕魔力外袍-LT", "description": "系列 : 鎧甲",
        "slot_count": 1, "class_num": 2, "equip_type": "armor",
        "stat_vector": [10, 0, 2], "onstart_equip_src": "function() end",
        "combi_ids": [2000002553],
    }])
    row = c.execute(
        "SELECT display_name, stat_vector, combi_ids FROM items WHERE item_id=450263"
    ).fetchone()
    assert row[0] == "月全蝕魔力外袍-LT"
    assert json.loads(row[1]) == [10, 0, 2]
    assert json.loads(row[2]) == [2000002553]


def test_insert_items_none_fields_stay_null():
    c = _conn()
    db.insert_items(c, [{
        "item_id": 1, "internal_name": None, "display_name": None,
        "description": "", "slot_count": None, "class_num": None,
        "equip_type": None, "stat_vector": None,
        "onstart_equip_src": None, "combi_ids": None,
    }])
    row = c.execute("SELECT stat_vector, combi_ids FROM items WHERE item_id=1").fetchone()
    assert row == (None, None)


def test_insert_combos():
    c = _conn()
    db.insert_combos(c, {2000000007: {
        "member_item_ids": [4244, 4299], "onstart_src": "function() end"}})
    row = c.execute(
        "SELECT member_item_ids, onstart_src FROM combos WHERE combo_id=2000000007"
    ).fetchone()
    assert json.loads(row[0]) == [4244, 4299]
    assert row[1] == "function() end"


def test_insert_enchants():
    c = _conn()
    db.insert_enchants(c, [{
        "table_index": 10004, "target_internal_names": ["Lunar_E_Armor_LT"],
        "slot_index": 1, "require_cost": '0, {"Pow_Meteorite_Fragment", 5}',
        "success_rate": 100000, "option_internal_name": "Star_Cluster_Of_Pow1",
        "option_weight": 13600,
    }])
    row = c.execute(
        "SELECT target_internal_names, option_weight FROM enchant_tables"
    ).fetchone()
    assert json.loads(row[0]) == ["Lunar_E_Armor_LT"]
    assert row[1] == 13600


def test_insert_skills_roundtrip():
    c = _conn()
    db.insert_skills(c, [{
        "skill_id": 2336, "internal_name": "SR_KNUCKLEARROW", "skill_name": "拳刃箭矢",
    }])
    row = c.execute(
        "SELECT internal_name, skill_name FROM skills WHERE skill_id=2336"
    ).fetchone()
    assert row == ("SR_KNUCKLEARROW", "拳刃箭矢")


def test_meta_roundtrip():
    c = _conn()
    db.set_meta(c, "grf_fingerprint", "123:456")
    assert db.get_meta(c, "grf_fingerprint") == "123:456"
    assert db.get_meta(c, "nope") is None


def test_create_twice_resets():
    c = _conn()
    db.insert_items(c, [{
        "item_id": 1, "internal_name": None, "display_name": None,
        "description": "", "slot_count": None, "class_num": None,
        "equip_type": None, "stat_vector": None,
        "onstart_equip_src": None, "combi_ids": None,
    }])
    db.create(c)
    assert c.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
