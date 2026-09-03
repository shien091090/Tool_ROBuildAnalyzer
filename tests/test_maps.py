import sqlite3
import tempfile
import os
import pytest
import gc
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
        cursor.close()
        conn.close()
        gc.collect()  # Force garbage collection to release file locks on Windows

        skill_map = maps.load_skill_map(db_path)
        assert skill_map[5015] == "劍術訓練"
        assert skill_map[1234] == "火球"
        assert len(skill_map) == 2


def test_load_skill_map_closes_connection():
    # Behavioral test: verify connection is actually closed by attempting to delete the file
    # On Windows, a file with an open handle cannot be deleted (raises PermissionError)
    db_path = None
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (skill_id INTEGER PRIMARY KEY, skill_name TEXT)")
        cursor.execute("INSERT INTO skills VALUES (5015, '劍術訓練')")
        conn.commit()
        cursor.close()
        conn.close()
        gc.collect()

        # Call load_skill_map
        skill_map = maps.load_skill_map(db_path)
        assert skill_map[5015] == "劍術訓練"

        # Try to delete the file - this will raise PermissionError if connection is still open (on Windows)
        # If this passes, the connection was properly closed
        try:
            os.remove(db_path)
        except PermissionError:
            pytest.fail("Database file still locked after load_skill_map - connection not closed properly")


def test_load_skill_map_missing_table():
    # Verify that OperationalError is raised when skills table does not exist
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        gc.collect()  # Force garbage collection to release file locks on Windows

        with pytest.raises(sqlite3.OperationalError):
            maps.load_skill_map(db_path)
        gc.collect()  # Release file locks before tempdir cleanup


def test_make_maps():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE skills (skill_id INTEGER PRIMARY KEY, skill_name TEXT)")
        cursor.execute("INSERT INTO skills VALUES (5015, '劍術訓練')")
        conn.commit()
        cursor.close()
        conn.close()
        gc.collect()  # Force garbage collection to release file locks on Windows

        effect_maps = maps.make_maps(db_path)
        assert isinstance(effect_maps.skill_map, dict)
        assert effect_maps.skill_map[5015] == "劍術訓練"
        gc.collect()  # Release file locks before tempdir cleanup
