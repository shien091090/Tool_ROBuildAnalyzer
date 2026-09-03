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


def test_fingerprint_and_date_written(tmp_path):
    report, conn = _run(tmp_path)
    fp = conn.execute(
        "SELECT value FROM import_meta WHERE key='grf_fingerprint'").fetchone()
    assert fp[0] == "123:456"
    assert conn.execute(
        "SELECT value FROM import_meta WHERE key='import_date'").fetchone() is not None
