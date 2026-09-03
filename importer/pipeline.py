import datetime
import sqlite3
from collections import defaultdict

from importer import db
from importer.parsers import enchant, equipment_properties, iteminfo, itemdbname


def run(lua_texts: dict[str, str], db_path: str, grf_fingerprint: str) -> dict:
    info_rows = iteminfo.parse(lua_texts["iteminfo"])
    name_to_id = itemdbname.parse(lua_texts["itemdbname"])
    id_to_name = {v: k for k, v in name_to_id.items()}
    equip_rows = {r["item_id"]: r for r in
                  equipment_properties.parse(lua_texts["equipment_properties"])}
    combos = equipment_properties.parse_combiitem(lua_texts["equipment_properties"])
    enchant_rows = enchant.parse(lua_texts["enchant"])

    info_by_id = {r["item_id"]: r for r in info_rows}
    iteminfo_duplicate_id_count = len(info_rows) - len(info_by_id)

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
        "iteminfo_duplicate_id_count": iteminfo_duplicate_id_count,
    }
