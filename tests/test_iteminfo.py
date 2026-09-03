from importer.parsers.iteminfo import parse

SAMPLE = """
tbl = {
[18675] = {unidentifiedDisplayName = "帽子", unidentifiedResourceName = "캡",
unidentifiedDescriptionName = {"尚未鑑定；可用[放大鏡]來鑑定物品。."}, identifiedDisplayName = "青蘋果頭套", identifiedResourceName = "청사과모자",
identifiedDescriptionName = {"青蘋果放在頭上讓人想咬一口。", "DEX+2, HIT+5, ", "系列 : ^777777頭具^000000 防禦 :  ^7777773^000000", "位置 :  ^777777頭上^000000 重量 : ^77777720^000000", "要求等級 :  ^77777720^000000", "裝備 : ^777777初學者以外的全職業^000000"}, slotCount = 1, ClassNum = 0},
[4001] = {unidentifiedDisplayName = "卡片", unidentifiedResourceName = "이름없는카드",
unidentifiedDescriptionName = {"..."}, identifiedDisplayName = "波利卡片", identifiedResourceName = "이름없는카드",
identifiedDescriptionName = {"LUK+2。", "完全迴避+1。", "系列 : ^777777卡片^000000", "裝置 : ^777777鎧甲^000000", "重量 : ^7777771^000000"}, slotCount = 0, ClassNum = 0, EffectID = 1186},
}
"""


def test_parse_normal_item():
    items = {row["item_id"]: row for row in parse(SAMPLE)}
    hat = items[18675]
    assert hat["display_name"] == "青蘋果頭套"
    assert hat["slot_count"] == 1
    assert hat["class_num"] == 0
    assert hat["effect_id"] is None
    assert "DEX+2, HIT+5, " in hat["description_lines"]


def test_parse_card_with_effect_id():
    items = {row["item_id"]: row for row in parse(SAMPLE)}
    card = items[4001]
    assert card["display_name"] == "波利卡片"
    assert card["description_lines"][0] == "LUK+2。"
    assert card["description_lines"][1] == "完全迴避+1。"
    assert card["effect_id"] == 1186
