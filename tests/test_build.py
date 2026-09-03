import json

import pytest

from app.core.build import GRADE_LEVELS, SLOT_IDS, load_build, load_character


def test_slot_ids_has_20_keys():
    assert len(SLOT_IDS) == 20


def test_slot_ids_known_values():
    # 一般裝備(spot check per task-11 brief 裝備介面對照)
    assert SLOT_IDS["armor"] == 2
    assert SLOT_IDS["shield"] == 3
    assert SLOT_IDS["weapon"] == 4
    assert SLOT_IDS["garment"] == 5
    assert SLOT_IDS["shoes"] == 6
    assert SLOT_IDS["acc_r"] == 7
    assert SLOT_IDS["acc_l"] == 8
    assert SLOT_IDS["head_top"] == 10
    assert SLOT_IDS["head_mid"] == 11
    assert SLOT_IDS["head_low"] == 12
    # 影子裝備(ItemSearchApp.py:2095-2098 equip_sitetype映射逐字採用)
    assert SLOT_IDS["shadow_armor"] == 30
    assert SLOT_IDS["shadow_gauntlet"] == 31
    assert SLOT_IDS["shadow_shield"] == 32
    assert SLOT_IDS["shadow_shoes"] == 33
    assert SLOT_IDS["shadow_earring"] == 34
    assert SLOT_IDS["shadow_pendant"] == 35
    # 服飾(自訂編號900起)
    assert SLOT_IDS["costume_top"] == 900
    assert SLOT_IDS["costume_mid"] == 901
    assert SLOT_IDS["costume_low"] == 902
    assert SLOT_IDS["costume_garment"] == 903


def test_slot_ids_insertion_order_is_armor_weapon_type_slots_first():
    # aggregate.evaluate_build relies on this literal insertion order.
    keys = list(SLOT_IDS.keys())
    general_slots = [
        "armor", "weapon", "shield", "garment", "shoes", "acc_r", "acc_l",
        "head_top", "head_mid", "head_low",
    ]
    assert keys[:10] == general_slots
    assert keys[10:16] == [
        "shadow_armor", "shadow_gauntlet", "shadow_shield",
        "shadow_shoes", "shadow_earring", "shadow_pendant",
    ]
    assert keys[16:] == ["costume_top", "costume_mid", "costume_low", "costume_garment"]


def test_grade_levels():
    assert GRADE_LEVELS == {"none": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def _spec_build_json():
    # spec §6 sample (docs/superpowers/specs/2026-09-03-robuildanalyzer-design.md)
    return {
        "name": "PD向物理配置",
        "slots": {
            "armor": {
                "item_id": 450263,
                "refine": 13,
                "grade": "A",
                "cards": [4140],
                "enchants": ["Star_Cluster_Of_Pow3", "Wolf_Orb_Str_2", None],
                "cost_targets": {
                    "refine_from": 0,
                    "grade_from": "none",
                    "enchant_strategy": "last_slot_only",
                },
            }
        },
    }


def test_load_build_roundtrip_spec_sample(tmp_path):
    path = tmp_path / "build.json"
    path.write_text(json.dumps(_spec_build_json(), ensure_ascii=False), encoding="utf-8")

    build = load_build(path)

    assert build.name == "PD向物理配置"
    assert set(build.slots.keys()) == {"armor"}
    slot = build.slots["armor"]
    assert slot.item_id == 450263
    assert slot.refine == 13
    assert slot.grade == "A"
    assert slot.cards == [4140]
    assert slot.enchants == ["Star_Cluster_Of_Pow3", "Wolf_Orb_Str_2", None]


def test_load_build_ignores_cost_targets_and_applies_defaults(tmp_path):
    data = {
        "name": "極簡配裝",
        "slots": {
            "weapon": {"item_id": 1001},
        },
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    build = load_build(path)

    slot = build.slots["weapon"]
    assert slot.item_id == 1001
    assert slot.refine == 0
    assert slot.grade == "none"
    assert slot.cards == []
    assert slot.enchants == []


def _spec_character_json():
    # spec §5.2 sample
    return {
        "name": "主帳PD",
        "job": 4055,
        "base_lv": 260,
        "job_lv": 55,
        "stats": {"STR": 130, "AGI": 90, "VIT": 100, "INT": 1, "DEX": 90, "LUK": 30},
        "traits": {"POW": 100, "STA": 60, "WIS": 0, "SPL": 0, "CON": 80, "CRT": 20},
        "skills": {"5015": 10},
    }


def test_load_character_roundtrip_spec_sample(tmp_path):
    path = tmp_path / "character.json"
    path.write_text(json.dumps(_spec_character_json(), ensure_ascii=False), encoding="utf-8")

    character = load_character(path)

    assert character.name == "主帳PD"
    assert character.job == 4055
    assert character.base_lv == 260
    assert character.job_lv == 55
    assert character.stats == {"STR": 130, "AGI": 90, "VIT": 100, "INT": 1, "DEX": 90, "LUK": 30}
    assert character.traits == {"POW": 100, "STA": 60, "WIS": 0, "SPL": 0, "CON": 80, "CRT": 20}
    # JSON object keys are always strings; skills must come back int-keyed.
    assert character.skills == {5015: 10}
    assert all(isinstance(k, int) for k in character.skills)


def test_load_build_unknown_slot_key_raises(tmp_path):
    data = {
        "name": "壞配裝",
        "slots": {
            "weaposn": {"item_id": 1001},  # typo'd slot key
        },
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="weaposn"):
        load_build(path)


def test_load_build_bad_grade_raises(tmp_path):
    data = {
        "name": "壞配裝",
        "slots": {
            "armor": {"item_id": 2001, "grade": "S"},  # not a valid GRADE_LEVELS key
        },
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="S"):
        load_build(path)


def test_load_character_empty_skills_defaults(tmp_path):
    data = {
        "name": "空技能角色",
        "job": 1,
        "base_lv": 1,
        "job_lv": 1,
        "stats": {},
        "traits": {},
    }
    path = tmp_path / "character.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    character = load_character(path)

    assert character.skills == {}
