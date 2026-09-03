from importer.parsers.equipment_properties import parse, parse_combiitem

SAMPLE = """
Item = {
  [13200] = {
    Type = "ammo",
    Stat = {0, 25}
  },
  [2153] = {
    Type = "armor",
    Stat = {
      120, 0, 0
    },
    OnStartEquip = function()
      local temp = 0
      if GetRefineLevel(3) > 5 then
        temp = (GetRefineLevel(3) - 5) * 2
      end
      AddDamage_SKID(1, 2310, 20 + temp)
    end,
    Combiitem = {
      2000000150,
      2000000694
    }
  },
  [4001] = {
    Type = "card",
    OnStartEquip = function()
      AddExtParam(0, 108, 2)
      AddExtParam(0, 51, 10)
    end,
    Combiitem = {2000000001, 2000001028}
  }
}
"""


def test_parse_ammo_no_onstart():
    rows = {row["item_id"]: row for row in parse(SAMPLE)}
    ammo = rows[13200]
    assert ammo["equip_type"] == "ammo"
    assert ammo["stat_vector"] == [0, 25]
    assert ammo["onstart_equip_src"] is None
    assert ammo["combi_item_ids"] is None


def test_parse_armor_with_refine_logic_and_combi():
    rows = {row["item_id"]: row for row in parse(SAMPLE)}
    armor = rows[2153]
    assert armor["equip_type"] == "armor"
    assert armor["stat_vector"] == [120, 0, 0]
    assert "GetRefineLevel(3)" in armor["onstart_equip_src"]
    assert armor["onstart_equip_src"].startswith("function()")
    assert armor["combi_item_ids"] == [2000000150, 2000000694]


def test_parse_armor_onstart_captures_full_body_past_nested_if():
    # Regression: OnStartEquip bodies commonly contain a nested if/end block
    # (e.g. refine-level bonuses) BEFORE further statements. The extracted
    # onstart_equip_src must span the whole function body up to the
    # function's OWN closing 'end', not stop at the nested if's 'end'.
    rows = {row["item_id"]: row for row in parse(SAMPLE)}
    armor = rows[2153]
    src = armor["onstart_equip_src"]
    assert src is not None
    # The nested if-block's own "end" must not be mistaken for the function's end:
    # everything after it (the AddDamage_SKID call) must still be present.
    assert "AddDamage_SKID(1, 2310, 20 + temp)" in src
    # The captured source must end with the function's own closing 'end'.
    assert src.rstrip().endswith("end")
    # Sanity: the nested if's "end" appears strictly before the trailing call.
    if_end_pos = src.index("end", src.index("if GetRefineLevel"))
    call_pos = src.index("AddDamage_SKID(1, 2310, 20 + temp)")
    assert if_end_pos < call_pos


def test_parse_card_with_addextparam():
    rows = {row["item_id"]: row for row in parse(SAMPLE)}
    card = rows[4001]
    assert card["equip_type"] == "card"
    assert card["stat_vector"] is None
    assert "AddExtParam(0, 108, 2)" in card["onstart_equip_src"]
    assert card["combi_item_ids"] == [2000000001, 2000001028]


# EquipmentProperties.lua declares FIVE sibling top-level tables:
# Item, Combiitem, SkillGroup, RefiningBonus, GradeBonus. Their keys overlap
# with real item ids (e.g. SkillGroup has [2000] and [5001], which are real
# items 破壞之杖 and 耳機), so a global unbounded `[N] = {` scan silently
# overwrote those items' real equipment data with sibling-table garbage.
SIBLING_TABLES_SAMPLE = """
Item = {
  [100] = { Type = "armor", Stat = {1, 2} }
}
Combiitem = {
  [100] = { Item = {999, 998} }
}
SkillGroup = {
  [100] = {19, 14}
}
"""


def test_parse_ignores_sibling_top_level_tables_with_colliding_keys():
    rows = parse(SIBLING_TABLES_SAMPLE)
    assert len(rows) == 1
    assert rows[0]["item_id"] == 100
    # Must be the Item-table version, not the Combiitem/SkillGroup entry.
    assert rows[0]["equip_type"] == "armor"
    assert rows[0]["stat_vector"] == [1, 2]
    # The Combiitem entry's nested `Item = {999, 998}` array must NOT have
    # leaked in as this item's combi_item_ids.
    assert rows[0]["combi_item_ids"] is None


COMBIITEM_SAMPLE = """
Item = {
  [4244] = {
    Type = "card",
    Combiitem = {2000000007}
  }
}
Combiitem = {
  [2000000007] = {
    Item = {
      4244,
      4299,
      4229,
      4313
    },
    OnStartEquip = function()
      AddExtParam(0, 47, 3)
      if GetRefineLevel(3) > 5 then
        AddExtParam(0, 45, 3)
      end
    end
  },
  [2000000008] = {
    Item = {4193, 4294}
  }
}
SkillGroup = {
  [2000000007] = {19}
}
"""


def test_parse_combiitem_extracts_members_and_onstart_src():
    combos = parse_combiitem(COMBIITEM_SAMPLE)
    assert set(combos) == {2000000007, 2000000008}

    combo = combos[2000000007]
    assert combo["member_item_ids"] == [4244, 4299, 4229, 4313]
    src = combo["onstart_src"]
    assert src is not None
    assert src.startswith("function()")
    # Same func_start-not-paren_close convention as parse(): the nested if's
    # own "end" must not truncate the captured source.
    assert "AddExtParam(0, 45, 3)" in src
    assert src.rstrip().endswith("end")


def test_parse_combiitem_handles_entry_without_onstart():
    combos = parse_combiitem(COMBIITEM_SAMPLE)
    assert combos[2000000008]["member_item_ids"] == [4193, 4294]
    assert combos[2000000008]["onstart_src"] is None


def test_parse_combiitem_ignores_nested_combiitem_field():
    # The FIRST textual `Combiitem = {` in the real file is the nested field
    # inside an Item entry, not the top-level table. Resolving the header
    # naively would return {2000000007} (a key list) as if it were the table.
    combos = parse_combiitem(COMBIITEM_SAMPLE)
    assert 4244 not in combos
    assert 2000000007 in combos


def test_parse_combiitem_missing_table_returns_empty():
    assert parse_combiitem(SAMPLE) == {}


def test_parse_missing_item_table_returns_empty():
    assert parse("SkillGroup = {\n  [1000] = {19}\n}\n") == []
