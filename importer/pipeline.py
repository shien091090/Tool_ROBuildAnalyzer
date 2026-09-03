import datetime
import sqlite3
from collections import defaultdict

from importer import db
from importer.parsers import enchant, equipment_properties, iteminfo, itemdbname, skillinfo


def run(lua_texts: dict[str, str], db_path: str, grf_fingerprint: str) -> dict:
    info_rows = iteminfo.parse(lua_texts["iteminfo"])
    name_to_id = itemdbname.parse(lua_texts["itemdbname"])
    id_to_name = {v: k for k, v in name_to_id.items()}
    equip_rows = {r["item_id"]: r for r in
                  equipment_properties.parse(lua_texts["equipment_properties"])}
    combos = equipment_properties.parse_combiitem(lua_texts["equipment_properties"])
    enchant_rows = enchant.parse(lua_texts["enchant"])

    info_by_id = {r["item_id"]: r for r in info_rows}
    # 超額列數(同item_id在iteminfo原始資料中被定義超過一次而多出來的列數), 非重複ID個數
    iteminfo_duplicate_row_count = len(info_rows) - len(info_by_id)

    items = []
    for info in info_by_id.values():
        iid = info["item_id"]
        eq = equip_rows.get(iid, {})
        items.append({
            "item_id": iid,
            "internal_name": id_to_name.get(iid),
            "display_name": info["display_name"],
            "description": "\n".join(info["description_lines"]),
            "slot_count": info["slot_count"],
            "class_num": info["class_num"],
            "equip_type": eq.get("equip_type"),
            "stat_vector": eq.get("stat_vector"),
            "onstart_equip_src": eq.get("onstart_equip_src"),
            "combi_ids": eq.get("combi_item_ids"),
        })

    # skillid/skillinfolist是選配的(既有測試/呼叫端不一定會傳), 缺任一個就跳過技能匯入
    skill_rows = []
    skills_unmatched_count = 0
    skills_corrupted_count = 0
    skillid_text = lua_texts.get("skillid")
    skillinfolist_text = lua_texts.get("skillinfolist")
    if skillid_text is not None and skillinfolist_text is not None:
        skillid_map = skillinfo.parse_skillid(skillid_text)
        info_map, skills_corrupted_count = skillinfo.parse_skillinfolist(skillinfolist_text)
        for internal_name, info in info_map.items():
            skill_id = skillid_map.get(internal_name)
            if skill_id is None:
                skills_unmatched_count += 1
                continue
            skill_rows.append({
                "skill_id": skill_id,
                "internal_name": internal_name,
                "skill_name": info["skill_name"],
            })

    weight_sums = defaultdict(int)
    for r in enchant_rows:
        weight_sums[(r["table_index"], r["slot_index"])] += r["option_weight"]
    anomaly_count = sum(1 for total in weight_sums.values() if total != 500000)

    conn = sqlite3.connect(db_path)
    try:
        db.create(conn)
        db.insert_items(conn, items)
        db.insert_combos(conn, combos)
        db.insert_enchants(conn, enchant_rows)
        db.insert_skills(conn, skill_rows)
        db.set_meta(conn, "grf_fingerprint", grf_fingerprint)
        db.set_meta(conn, "import_date", datetime.date.today().isoformat())
        conn.commit()
    finally:
        conn.close()

    return {
        "items_count": len(items),
        "items_with_effect_count": sum(
            1 for i in items if i["onstart_equip_src"]),
        "items_missing_display_name_count": sum(
            1 for i in items if not i["display_name"]),
        "combos_count": len(combos),
        "enchant_rules_count": len(enchant_rows),
        "enchant_tables_count": len({r["table_index"] for r in enchant_rows}),
        "enchant_weight_anomaly_count": anomaly_count,
        "iteminfo_duplicate_row_count": iteminfo_duplicate_row_count,
        "equip_items_not_in_iteminfo_count": sum(
            1 for iid in equip_rows if iid not in info_by_id),
        "itemdbname_alias_collision_count": len(name_to_id) - len(id_to_name),
        "items_missing_internal_name_count": sum(
            1 for i in items if i["internal_name"] is None),
        "decode_replacement_char_count": sum(
            t.count("�") for t in lua_texts.values()),
        "skills_count": len(skill_rows),
        "skills_unmatched_count": skills_unmatched_count,
        "skills_corrupted_count": skills_corrupted_count,
    }
