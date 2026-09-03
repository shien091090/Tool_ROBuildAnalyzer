import json
import sqlite3

_DDL = """
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS combos;
DROP TABLE IF EXISTS enchant_tables;
DROP TABLE IF EXISTS import_meta;
CREATE TABLE items(
  item_id INTEGER PRIMARY KEY,
  internal_name TEXT,
  display_name TEXT,
  description TEXT,
  slot_count INTEGER,
  class_num INTEGER,
  equip_type TEXT,
  stat_vector TEXT,
  onstart_equip_src TEXT,
  combi_ids TEXT
);
CREATE TABLE combos(
  combo_id INTEGER PRIMARY KEY,
  member_item_ids TEXT NOT NULL,
  onstart_src TEXT
);
CREATE TABLE enchant_tables(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_index INTEGER NOT NULL,
  target_internal_names TEXT NOT NULL,
  slot_index INTEGER NOT NULL,
  require_cost TEXT,
  success_rate INTEGER,
  option_internal_name TEXT NOT NULL,
  option_weight INTEGER NOT NULL
);
CREATE TABLE import_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _j(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def create(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def insert_items(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO items(item_id, internal_name, display_name, description,"
        " slot_count, class_num, equip_type, stat_vector, onstart_equip_src, combi_ids)"
        " VALUES(:item_id, :internal_name, :display_name, :description,"
        " :slot_count, :class_num, :equip_type, :stat_vector, :onstart_equip_src, :combi_ids)",
        [{**r, "stat_vector": _j(r["stat_vector"]), "combi_ids": _j(r["combi_ids"])}
         for r in rows],
    )


def insert_combos(conn: sqlite3.Connection, combos: dict) -> None:
    conn.executemany(
        "INSERT INTO combos(combo_id, member_item_ids, onstart_src) VALUES(?,?,?)",
        [(cid, _j(v["member_item_ids"]), v["onstart_src"]) for cid, v in combos.items()],
    )


def insert_enchants(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO enchant_tables(table_index, target_internal_names, slot_index,"
        " require_cost, success_rate, option_internal_name, option_weight)"
        " VALUES(:table_index, :target_internal_names, :slot_index,"
        " :require_cost, :success_rate, :option_internal_name, :option_weight)",
        [{**r, "target_internal_names": _j(r["target_internal_names"])} for r in rows],
    )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO import_meta(key, value) VALUES(?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str):
    row = conn.execute("SELECT value FROM import_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None
