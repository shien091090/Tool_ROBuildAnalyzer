import json
import sqlite3
from importer import db
from app.core.db_reader import DbReader, EnchantRow, ItemRecord


def _setup_db(tmp_path):
    """Create a test database with sample data."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    db.create(conn)

    # Insert test items
    db.insert_items(
        conn,
        [
            {
                "item_id": 450263,
                "internal_name": "Lunar_E_Armor_LT",
                "display_name": "月全蝕魔力外袍-LT",
                "description": "This is a great armor",
                "slot_count": 1,
                "class_num": 2,
                "equip_type": "armor",
                "stat_vector": [10, 0, 2],
                "onstart_equip_src": "AddDamage_CRI(1, 7)",
                "combi_ids": [2000000007],
            },
            {
                "item_id": 999999,
                "internal_name": None,
                "display_name": "Mystery Item",
                "description": "No internal name",
                "slot_count": 0,
                "class_num": 0,
                "equip_type": None,
                "stat_vector": None,
                "onstart_equip_src": None,
                "combi_ids": None,
            },
            {
                "item_id": 450264,
                "internal_name": "Another_Armor",
                "display_name": None,
                "description": "No display name",
                "slot_count": 2,
                "class_num": 1,
                "equip_type": "armor",
                "stat_vector": [5, 3, 1],
                "onstart_equip_src": None,
                "combi_ids": [2000000008, 2000000009],
            },
        ],
    )

    # Insert test combos
    db.insert_combos(
        conn,
        {
            2000000007: {
                "member_item_ids": [450263, 4299],
                "onstart_src": "AddExtParam(0, 242, 2)",
            },
            2000000008: {
                "member_item_ids": [450264],
                "onstart_src": None,
            },
        },
    )

    # Insert test skills
    db.insert_skills(
        conn,
        [
            {"skill_id": 2336, "internal_name": "SR_KNUCKLEARROW", "skill_name": "拳刃箭矢"},
            {"skill_id": 2335, "internal_name": "SR_LIGHTNINGWALK", "skill_name": "電光步"},
        ],
    )

    # Insert test enchant rows: table 1 = target item, table 2 = unrelated
    # item(用來驗證LIKE比對不會誤命中), 且slot 3同一option故意重複出現兩次
    # (模擬真實資料源本身的重複列, 讀取層不可自作主張去重)。
    db.insert_enchants(
        conn,
        [
            {
                "table_index": 1,
                "target_internal_names": ["Lunar_E_Armor_LT"],
                "slot_index": 3,
                "require_cost": '1000, {"Mat_A", 2}',
                "success_rate": 100000,
                "option_internal_name": "OptA",
                "option_weight": 100,
            },
            {
                "table_index": 1,
                "target_internal_names": ["Lunar_E_Armor_LT"],
                "slot_index": 3,
                "require_cost": '1000, {"Mat_A", 2}',
                "success_rate": 100000,
                "option_internal_name": "OptA",
                "option_weight": 100,
            },
            {
                "table_index": 1,
                "target_internal_names": ["Lunar_E_Armor_LT"],
                "slot_index": 1,
                "require_cost": "500",
                "success_rate": 100000,
                "option_internal_name": "OptB",
                "option_weight": 50,
            },
            {
                "table_index": 2,
                "target_internal_names": ["Another_Armor"],
                "slot_index": 1,
                "require_cost": "999",
                "success_rate": 100000,
                "option_internal_name": "OptC",
                "option_weight": 1,
            },
        ],
    )

    conn.commit()
    conn.close()
    return db_path


def test_item_hit(tmp_path):
    """Test reading an existing item."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item(450263)
    assert item is not None
    assert item.item_id == 450263
    assert item.internal_name == "Lunar_E_Armor_LT"
    assert item.display_name == "月全蝕魔力外袍-LT"
    assert item.description == "This is a great armor"
    assert item.slot_count == 1
    assert item.equip_type == "armor"
    assert item.stat_vector == [10, 0, 2]
    assert item.onstart_equip_src == "AddDamage_CRI(1, 7)"
    assert item.combi_ids == [2000000007]

    reader.close()


def test_item_miss(tmp_path):
    """Test reading a non-existent item returns None."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item(999)
    assert item is None

    reader.close()


def test_item_with_null_fields(tmp_path):
    """Test reading an item with NULL fields."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item(999999)
    assert item is not None
    assert item.item_id == 999999
    assert item.internal_name is None
    assert item.display_name == "Mystery Item"
    assert item.stat_vector is None
    assert item.onstart_equip_src is None
    assert item.combi_ids is None

    reader.close()


def test_item_by_internal_name_hit(tmp_path):
    """Test reading an item by internal name."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item_by_internal_name("Lunar_E_Armor_LT")
    assert item is not None
    assert item.item_id == 450263
    assert item.internal_name == "Lunar_E_Armor_LT"
    assert item.display_name == "月全蝕魔力外袍-LT"

    reader.close()


def test_item_by_internal_name_miss(tmp_path):
    """Test reading a non-existent internal name returns None."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item_by_internal_name("NonExistent_Item")
    assert item is None

    reader.close()


def test_combo_hit_with_onstart_src(tmp_path):
    """Test reading an existing combo with onstart_src."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    result = reader.combo(2000000007)
    assert result is not None
    members, onstart_src = result
    assert members == [450263, 4299]
    assert onstart_src == "AddExtParam(0, 242, 2)"

    reader.close()


def test_combo_hit_without_onstart_src(tmp_path):
    """Test reading a combo with NULL onstart_src."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    result = reader.combo(2000000008)
    assert result is not None
    members, onstart_src = result
    assert members == [450264]
    assert onstart_src is None

    reader.close()


def test_combo_miss(tmp_path):
    """Test reading a non-existent combo returns None."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    result = reader.combo(999)
    assert result is None

    reader.close()


def test_json_decode_stat_vector(tmp_path):
    """Test JSON decoding of stat_vector."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item(450264)
    assert item is not None
    assert item.stat_vector == [5, 3, 1]
    assert isinstance(item.stat_vector, list)

    reader.close()


def test_json_decode_combi_ids(tmp_path):
    """Test JSON decoding of combi_ids."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item(450264)
    assert item is not None
    assert item.combi_ids == [2000000008, 2000000009]
    assert isinstance(item.combi_ids, list)

    reader.close()


def test_json_decode_member_item_ids(tmp_path):
    """Test JSON decoding of member_item_ids in combo."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    result = reader.combo(2000000007)
    assert result is not None
    members, _ = result
    assert members == [450263, 4299]
    assert isinstance(members, list)

    reader.close()


def test_context_manager(tmp_path):
    """Test DbReader as context manager."""
    db_path = _setup_db(tmp_path)

    with DbReader(db_path) as reader:
        item = reader.item(450263)
        assert item is not None
        assert item.item_id == 450263


def test_close_method(tmp_path):
    """Test explicit close method."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    item = reader.item(450263)
    assert item is not None

    # After close, connection should be closed
    reader.close()
    # Trying to use reader after close should raise an error
    try:
        reader.item(450263)
        assert False, "Expected an error after close"
    except sqlite3.ProgrammingError:
        pass  # Expected


def test_enchant_table_for_item_hit(tmp_path):
    """Test resolving an item's enchant table_index via target_internal_names."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    assert reader.enchant_table_for_item("Lunar_E_Armor_LT") == 1
    assert reader.enchant_table_for_item("Another_Armor") == 2

    reader.close()


def test_enchant_table_for_item_miss(tmp_path):
    """Test that an item not present in any table's target list returns None."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    assert reader.enchant_table_for_item("No_Such_Item") is None

    reader.close()


def test_enchant_rows_ordered_by_slot_desc_and_not_deduped(tmp_path):
    """Test that enchant_rows returns slot_index descending and keeps duplicate
    rows as-is(分母資料驅動需要看到原始重複列, 不能被讀取層去重)."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    rows = reader.enchant_rows(1)
    assert [r.slot_index for r in rows] == [3, 3, 1]
    assert rows[0] == EnchantRow(
        slot_index=3, require_cost='1000, {"Mat_A", 2}', option_internal_name="OptA", option_weight=100
    )
    assert rows[2] == EnchantRow(
        slot_index=1, require_cost="500", option_internal_name="OptB", option_weight=50
    )

    reader.close()


def test_enchant_rows_unknown_table_returns_empty(tmp_path):
    """Test that a table_index with no rows returns an empty list, not an error."""
    db_path = _setup_db(tmp_path)
    reader = DbReader(db_path)

    assert reader.enchant_rows(999) == []

    reader.close()
