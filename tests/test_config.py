import json
import os
import pytest
from importer import config


def test_luadec_and_unluac_paths_are_absolute():
    assert os.path.isabs(config.LUADEC_EXE)
    assert os.path.isabs(config.UNLUAC_JAR)
    assert config.LUADEC_EXE.endswith(os.path.join("data", "tools", "luadec.exe"))
    assert config.UNLUAC_JAR.endswith(os.path.join("data", "tools", "unluac.jar"))


def test_load_reads_fields(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "dro_path": "D:\\DRO", "java_exe": "java", "db_path": "data/x.db"
    }), encoding="utf-8")
    cfg = config.load(str(p))
    assert cfg.dro_path == "D:\\DRO"
    assert cfg.java_exe == "java"
    assert cfg.db_path == "data/x.db"
    assert cfg.data_grf_path.endswith("data.grf")
    assert cfg.iteminfo_lub_path.endswith("iteminfo_new.lub")


def test_load_missing_file_raises_with_hint(tmp_path):
    with pytest.raises(config.ConfigNotFoundError) as e:
        config.load(str(tmp_path / "nope.json"))
    assert "config.example.json" in str(e.value)
