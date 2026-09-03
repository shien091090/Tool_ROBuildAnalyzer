import sqlite3
import tempfile
import os
from app.core import maps


def test_effect_map_entries():
    assert maps.EFFECT_MAP[242] == "P.ATK"
    assert maps.EFFECT_MAP[51] == "完全迴避"


def test_race_map_all_species():
    assert maps.RACE_MAP[9999] == "全種族"


def test_stat_name_sets_armor():
    assert maps.STAT_NAME_SETS["armor"][10] == "防具等級"


def test_plain_effect_map_count():
    assert len(maps.PLAIN_EFFECT_MAP) == 8


def test_load_skill_map():
    # Create a temporary database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (skill_id INTEGER PRIMARY KEY, skill_name TEXT)")
        cursor.execute("INSERT INTO skills VALUES (5015, '劍術訓練')")
        cursor.execute("INSERT INTO skills VALUES (1234, '火球')")
        conn.commit()
        conn.close()

        skill_map = maps.load_skill_map(db_path)
        assert skill_map[5015] == "劍術訓練"
        assert skill_map[1234] == "火球"
        assert len(skill_map) == 2


def test_make_maps():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (skill_id INTEGER PRIMARY KEY, skill_name TEXT)")
        cursor.execute("INSERT INTO skills VALUES (5015, '劍術訓練')")
        conn.commit()
        conn.close()

        effect_maps = maps.make_maps(db_path)
        assert isinstance(effect_maps.skill_map, dict)
        assert effect_maps.skill_map[5015] == "劍術訓練"
