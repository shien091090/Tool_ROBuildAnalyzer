"""共用: 建一個帶items/combos/enchant_tables/skills/meta的小DB與builds/characters目錄, 回傳AnalyzerSession(task-4 brief)."""
import json
import sqlite3
from pathlib import Path

from app.core.session import AnalyzerSession
from importer import db


def _item(item_id, internal, name, desc, equip_type, slot_count=0, onstart=None, combi=None):
    return {"item_id": item_id, "internal_name": internal, "display_name": name, "description": desc,
            "slot_count": slot_count, "class_num": 0, "equip_type": equip_type, "stat_vector": None,
            "onstart_equip_src": onstart, "combi_ids": combi}


ITEMS = [
    _item(2001, "Test_Armor", "測試鎧甲", "系列 : ^777777鎧甲^000000\n裝備 : ^777777全職業^000000", "armor", 1, "AddExtParam(0, 41, 10)", [5001]),
    _item(3001, "Test_Card", "測試卡片", "系列 : ^777777卡片^000000\n裝備 : ^777777鎧甲^000000", "card", 0, "AddExtParam(0, 41, 5)", [5001]),
    _item(310001, "Opt_A", "詞條A", "A", "card", 0, "AddExtParam(0, 41, 1)"),
    _item(310002, "Opt_B", "詞條B", "B", "card", 0, "AddExtParam(0, 41, 2)"),
    _item(1001, "Test_Weapon", "測試武器", "系列 : ^777777雙手劍^000000\n裝備 : ^777777盧恩騎士系列^000000", "Mweapon", 2, "AddExtParam(0, 41, 20)"),
]
COMBOS = {5001: {"member_item_ids": [2001, 3001], "onstart_src": "AddExtParam(0, 41, 100)"}}
ENCHANTS = [
    {"table_index": 7, "target_internal_names": ["Test_Armor"], "slot_index": 3, "require_cost": None, "success_rate": 100, "option_internal_name": "Opt_A", "option_weight": 30},
    {"table_index": 7, "target_internal_names": ["Test_Armor"], "slot_index": 3, "require_cost": None, "success_rate": 100, "option_internal_name": "Opt_B", "option_weight": 10},
    {"table_index": 7, "target_internal_names": ["Test_Armor"], "slot_index": 2, "require_cost": None, "success_rate": 100, "option_internal_name": "Opt_A", "option_weight": 1},
]
SKILLS = [{"skill_id": 5015, "internal_name": "X", "skill_name": "測試技能"}]


def make_session(tmp_path: Path) -> AnalyzerSession:
    db_path = str(tmp_path / "s.db")
    conn = sqlite3.connect(db_path)
    db.create(conn)
    db.insert_items(conn, ITEMS)
    db.insert_combos(conn, COMBOS)
    db.insert_enchants(conn, ENCHANTS)
    db.insert_skills(conn, SKILLS)
    db.set_meta(conn, "import_date", "2026-09-04")
    conn.commit()
    conn.close()
    builds = tmp_path / "builds"
    builds.mkdir()
    chars = tmp_path / "characters"
    chars.mkdir()
    (builds / "a.json").write_text(json.dumps({"name": "A配裝", "slots": {
        "armor": {"item_id": 2001, "refine": 7, "cards": [3001], "enchants": ["Opt_A"]}}}, ensure_ascii=False), encoding="utf-8")
    (builds / "b.json").write_text(json.dumps({"name": "B配裝", "slots": {"weapon": {"item_id": 1001}}}, ensure_ascii=False), encoding="utf-8")
    (chars / "rk.json").write_text(json.dumps({"name": "測試RK", "job": 4252, "base_lv": 250, "job_lv": 50,
        "stats": {"STR": 100, "AGI": 1, "VIT": 1, "INT": 1, "DEX": 1, "LUK": 1}, "traits": {}, "skills": {}}, ensure_ascii=False), encoding="utf-8")
    return AnalyzerSession(db_path, builds_dir=str(builds), characters_dir=str(chars))
