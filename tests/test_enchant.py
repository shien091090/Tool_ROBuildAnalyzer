from importer.parsers.enchant import parse

SAMPLE = """
Table[1] = CreateEnchantInfo()
Table[1]:AddTargetItem("Gray_W_Suits")
Table[1]:AddTargetItem("Gray_W_Robe")
Table[1].Slot[3]:SetRequire(100000, {"Ep18_Amethyst_Fragment", 15})
Table[1].Slot[3]:SetSuccessRate(100000)
Table[1].Slot[3]:SetEnchant(0, "Wolf_Orb_Str_1", 9900)
Table[1].Slot[3]:SetEnchant(0, "Wolf_Orb_Dex_1", 9900)
Table[1].Slot[2]:SetRequire(150000, {"Ep18_Amethyst_Fragment", 25})
Table[1].Slot[2]:SetSuccessRate(100000)
Table[1].Slot[2]:SetEnchant(0, "Wolf_Orb_Str_1", 10001)
"""


def test_parse_enchant_accumulates_targets_and_slot_state():
    rows = parse(SAMPLE)
    assert len(rows) == 3

    row0 = rows[0]
    assert row0["table_index"] == 1
    assert row0["target_internal_names"] == ["Gray_W_Suits", "Gray_W_Robe"]
    assert row0["slot_index"] == 3
    assert row0["success_rate"] == 100000
    assert row0["option_internal_name"] == "Wolf_Orb_Str_1"
    assert row0["option_weight"] == 9900

    row2 = rows[2]
    assert row2["slot_index"] == 2
    assert row2["option_internal_name"] == "Wolf_Orb_Str_1"
    assert row2["option_weight"] == 10001
