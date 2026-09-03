import json
import sqlite3
from importer import pipeline

_ITEMINFO = """
tbl = {
  [450263] = {
    identifiedDisplayName = "月全蝕魔力外袍-LT",
    identifiedDescriptionName = { "第一行", "第二行" },
    slotCount = 1,
    ClassNum = 2,
  },
  [999999] = {
    slotCount = 0,
    ClassNum = 0,
  },
}
"""

_ITEMDBNAME = """
Lunar_E_Armor_LT = 450263
"""

_EQUIP_PROPS = """
Item = {
  [450263] = {
    Type = "armor",
    Stat = { 10, 0, 2 },
    OnStartEquip = function()
      AddDamage_CRI(1, 7)
    end,
    Combiitem = { 2000000007 }
  }
}
Combiitem = {
  [2000000007] = {
    Item = {450263, 4299},
    OnStartEquip = function()
      AddExtParam(0, 242, 2)
    end
  }
}
"""

_ENCHANT = """
Table[10004] = CreateEnchantInfo()
Table[10004]:AddTargetItem("Lunar_E_Armor_LT")
Table[10004].Slot[1]:SetRequire(0, {"Pow_Meteorite_Fragment", 5})
Table[10004].Slot[1]:SetSuccessRate(100000)
Table[10004].Slot[1]:SetEnchant(1, "Star_Cluster_Of_Pow1", 300000)
Table[10004].Slot[1]:SetEnchant(1, "Star_Cluster_Of_Crt1", 200000)
Table[10005] = CreateEnchantInfo()
Table[10005]:AddTargetItem("Other_Item")
Table[10005].Slot[2]:SetRequire(0, {"X", 1})
Table[10005].Slot[2]:SetSuccessRate(100000)
Table[10005].Slot[2]:SetEnchant(1, "A_1", 60000)
Table[10005].Slot[2]:SetEnchant(1, "B_1", 40000)
"""


def _run(tmp_path):
    db_path = str(tmp_path / "t.db")
    report = pipeline.run(
        {
            "iteminfo": _ITEMINFO,
            "itemdbname": _ITEMDBNAME,
            "equipment_properties": _EQUIP_PROPS,
            "enchant": _ENCHANT,
        },
        db_path,
        "123:456",
    )
    return report, sqlite3.connect(db_path)


def test_items_merged_across_sources(tmp_path):
    report, conn = _run(tmp_path)
    row = conn.execute(
        "SELECT internal_name, display_name, description, slot_count,"
        " equip_type, stat_vector, onstart_equip_src, combi_ids"
        " FROM items WHERE item_id=450263").fetchone()
    assert row[0] == "Lunar_E_Armor_LT"
    assert row[1] == "月全蝕魔力外袍-LT"
    assert row[2] == "第一行\n第二行"
    assert row[3] == 1
    assert row[4] == "armor"
    assert json.loads(row[5]) == [10, 0, 2]
    assert "AddDamage_CRI" in row[6]
    assert json.loads(row[7]) == [2000000007]


def test_item_without_equipment_entry_kept(tmp_path):
    report, conn = _run(tmp_path)
    row = conn.execute(
        "SELECT equip_type, onstart_equip_src FROM items WHERE item_id=999999").fetchone()
    assert row == (None, None)


def test_combos_stored(tmp_path):
    report, conn = _run(tmp_path)
    row = conn.execute(
        "SELECT member_item_ids, onstart_src FROM combos WHERE combo_id=2000000007").fetchone()
    assert json.loads(row[0]) == [450263, 4299]
    assert "AddExtParam" in row[1]


def test_report_counts(tmp_path):
    report, conn = _run(tmp_path)
    assert report["items_count"] == 2
    assert report["items_with_effect_count"] == 1
    assert report["items_missing_display_name_count"] == 1
    assert report["combos_count"] == 1
    assert report["enchant_rules_count"] == 4
    assert report["enchant_tables_count"] == 2
    # table10004 slot1總和=500000正常, table10005 slot2總和=100000 → 1組異常
    assert report["enchant_weight_anomaly_count"] == 1
    # 999999在iteminfo有定義但itemdbname無對應internal_name, 450263有 → 缺1個
    assert report["items_missing_internal_name_count"] == 1
    # equipment_properties只定義450263, 該id在iteminfo也有定義 → 0個孤兒
    assert report["equip_items_not_in_iteminfo_count"] == 0
    # itemdbname只有一筆別名, 無collision
    assert report["itemdbname_alias_collision_count"] == 0
    # fixture文字皆為乾淨字串, 無解碼替代字元
    assert report["decode_replacement_char_count"] == 0


_ITEMINFO_DUPLICATE = """
tbl = {
  [450263] = {
    identifiedDisplayName = "舊名稱",
    identifiedDescriptionName = { "第一行" },
    slotCount = 0,
    ClassNum = 0,
  },
  [450263] = {
    identifiedDisplayName = "新名稱",
    identifiedDescriptionName = { "第一行" },
    slotCount = 0,
    ClassNum = 0,
  },
}
"""


def test_duplicate_item_id_last_write_wins_and_counted(tmp_path):
    db_path = str(tmp_path / "dup.db")
    report = pipeline.run(
        {
            "iteminfo": _ITEMINFO_DUPLICATE,
            "itemdbname": _ITEMDBNAME,
            "equipment_properties": _EQUIP_PROPS,
            "enchant": _ENCHANT,
        },
        db_path,
        "123:456",
    )
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT display_name FROM items WHERE item_id=450263").fetchone()
    assert row[0] == "新名稱"
    assert report["items_count"] == 1
    assert report["iteminfo_duplicate_row_count"] == 1


_ITEMINFO_TRIPLICATE = """
tbl = {
  [450263] = {
    identifiedDisplayName = "名稱A",
    identifiedDescriptionName = { "第一行" },
    slotCount = 0,
    ClassNum = 0,
  },
  [450263] = {
    identifiedDisplayName = "名稱B",
    identifiedDescriptionName = { "第一行" },
    slotCount = 0,
    ClassNum = 0,
  },
  [450263] = {
    identifiedDisplayName = "名稱C",
    identifiedDescriptionName = { "第一行" },
    slotCount = 0,
    ClassNum = 0,
  },
}
"""


def test_triplicate_item_id_last_write_wins_and_counted(tmp_path):
    db_path = str(tmp_path / "triple.db")
    report = pipeline.run(
        {
            "iteminfo": _ITEMINFO_TRIPLICATE,
            "itemdbname": _ITEMDBNAME,
            "equipment_properties": _EQUIP_PROPS,
            "enchant": _ENCHANT,
        },
        db_path,
        "123:456",
    )
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT display_name FROM items WHERE item_id=450263").fetchone()
    assert row[0] == "名稱C"
    assert report["items_count"] == 1
    assert report["iteminfo_duplicate_row_count"] == 2


_EQUIP_PROPS_ORPHAN = """
Item = {
  [450263] = {
    Type = "armor",
    Stat = { 10, 0, 2 },
    OnStartEquip = function()
      AddDamage_CRI(1, 7)
    end,
    Combiitem = { 2000000007 }
  },
  [777777] = {
    Type = "weapon",
    Stat = { 1, 0, 0 },
  }
}
Combiitem = {
  [2000000007] = {
    Item = {450263, 4299},
    OnStartEquip = function()
      AddExtParam(0, 242, 2)
    end
  }
}
"""


def test_equip_item_not_in_iteminfo_counted_and_dropped(tmp_path):
    db_path = str(tmp_path / "orphan.db")
    report = pipeline.run(
        {
            "iteminfo": _ITEMINFO,
            "itemdbname": _ITEMDBNAME,
            "equipment_properties": _EQUIP_PROPS_ORPHAN,
            "enchant": _ENCHANT,
        },
        db_path,
        "123:456",
    )
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT item_id FROM items WHERE item_id=777777").fetchone()
    assert row is None
    assert report["equip_items_not_in_iteminfo_count"] == 1


def test_fingerprint_and_date_written(tmp_path):
    report, conn = _run(tmp_path)
    fp = conn.execute(
        "SELECT value FROM import_meta WHERE key='grf_fingerprint'").fetchone()
    assert fp[0] == "123:456"
    assert conn.execute(
        "SELECT value FROM import_meta WHERE key='import_date'").fetchone() is not None


_SKILLID = 'SKID = {SR_KNUCKLEARROW = 2336, SR_LIGHTNINGWALK = 2335}'

_SKILLINFOLIST = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.SR_KNUCKLEARROW] = {"SR_KNUCKLEARROW"; SkillName = "拳刃箭矢", MaxLv = 10, \n'
    'SpAmount = {12}, bSeperateLv = false, \n'
    'AttackRange = {7}}, \n'
    '[SKID.SR_LIGHTNINGWALK] = {"SR_LIGHTNINGWALK"; SkillName = "電光步", MaxLv = 5, \n'
    'SpAmount = {10}, bSeperateLv = false, \n'
    'AttackRange = {1}}, \n'
    # UNKNOWN_SKILL沒有出現在_SKILLID裡, 用來驗證skills_unmatched_count
    '[SKID.UNKNOWN_SKILL] = {"UNKNOWN_SKILL"; SkillName = "未知技能", MaxLv = 1, \n'
    'SpAmount = {1}, bSeperateLv = false, \n'
    'AttackRange = {1}}, \n'
    '}'
)


def _run_with_skills(tmp_path):
    db_path = str(tmp_path / "skills.db")
    report = pipeline.run(
        {
            "iteminfo": _ITEMINFO,
            "itemdbname": _ITEMDBNAME,
            "equipment_properties": _EQUIP_PROPS,
            "enchant": _ENCHANT,
            "skillid": _SKILLID,
            "skillinfolist": _SKILLINFOLIST,
        },
        db_path,
        "123:456",
    )
    return report, sqlite3.connect(db_path)


def test_skills_imported_and_joined(tmp_path):
    report, conn = _run_with_skills(tmp_path)
    row = conn.execute(
        "SELECT internal_name, skill_name FROM skills WHERE skill_id=2336").fetchone()
    assert row == ("SR_KNUCKLEARROW", "拳刃箭矢")
    assert report["skills_count"] == 2


def test_skills_unmatched_count(tmp_path):
    report, conn = _run_with_skills(tmp_path)
    # UNKNOWN_SKILL在skillinfolist有定義但skillid沒有對應id, 應被跳過且計入unmatched
    assert report["skills_unmatched_count"] == 1
    row = conn.execute(
        "SELECT * FROM skills WHERE internal_name='UNKNOWN_SKILL'").fetchone()
    assert row is None


def test_skills_lua_texts_optional_defaults_to_skip(tmp_path):
    # 既有測試不帶skillid/skillinfolist這兩個key, 應視為跳過技能匯入而非報錯
    report, conn = _run(tmp_path)
    assert report["skills_count"] == 0
    assert report["skills_unmatched_count"] == 0
    assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 0
