import sqlite3

import pytest

from app.core.aggregate import evaluate_build, make_context
from app.core.build import GRADE_LEVELS, SLOT_IDS, Build, Character, SlotConfig
from app.core.db_reader import DbReader
from app.core.entries import KIND_NUMERIC, KIND_UNRESOLVED
from app.core.maps import EffectMaps
from importer import db


def _setup_db(tmp_path):
    """Fixture DB for evaluate_build tests: 2 body items + 1 card + 1 enchant +
    3 combos (one applies via body items, one applies via a CARD member, one
    fails to establish because a member is unequipped) + 1 combo id that is
    referenced but never inserted (查無套裝)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    db.create(conn)

    db.insert_items(
        conn,
        [
            {
                "item_id": 2001,
                "internal_name": "Test_Armor",
                "display_name": "測試防具",
                "description": "d",
                "slot_count": 1,
                "class_num": 0,
                "equip_type": "armor",
                "stat_vector": None,
                # EnableSkill first (armor processed before weapon per
                # SLOT_IDS order) so weapon's GetSkillLevel condition resolves.
                "onstart_equip_src": "EnableSkill(63,5)\nAddDamage_CRI(1,7)",
                "combi_ids": [5001, 5002, 5003, 6001],
            },
            {
                "item_id": 1001,
                "internal_name": "Test_Weapon",
                "display_name": "測試武器",
                "description": "d",
                "slot_count": 0,
                "class_num": 0,
                "equip_type": "weapon",
                "stat_vector": None,
                "onstart_equip_src": "if GetSkillLevel(63) >= 5 then\nAddExtParam(1,52,3)\nend",
                "combi_ids": [5001],
            },
            {
                "item_id": 3001,
                "internal_name": "Test_Card",
                "display_name": "測試卡片",
                "description": "d",
                "slot_count": 0,
                "class_num": 0,
                "equip_type": "armor",
                "stat_vector": None,
                "onstart_equip_src": "AddExtParam(0, 242, 2)",
                "combi_ids": None,
            },
            {
                "item_id": 4001,
                "internal_name": "Test_Enchant_Str",
                "display_name": "測試詞條",
                "description": "d",
                "slot_count": 0,
                "class_num": 0,
                "equip_type": "armor",
                "stat_vector": None,
                "onstart_equip_src": "AddExtParam(0, 234, 1)",
                "combi_ids": None,
            },
            {
                "item_id": 7001,
                "internal_name": "Test_Garment",
                "display_name": "測試披風",
                "description": "d",
                "slot_count": 0,
                "class_num": 0,
                "equip_type": "armor",
                "stat_vector": None,
                # job_STR is not provided by the test character -> unresolved.
                "onstart_equip_src": "if job_STR >= 100 then\nAddExtParam(1,45,3)\nend",
                "combi_ids": None,
            },
        ],
    )

    db.insert_combos(
        conn,
        {
            5001: {"member_item_ids": [1001, 2001], "onstart_src": "AddExtParam(0, 242, 5)"},
            # 9998 is never equipped -> this combo never establishes.
            5002: {"member_item_ids": [2001, 9998], "onstart_src": "AddExtParam(0, 242, 999)"},
            6001: {"member_item_ids": [2001, 3001], "onstart_src": "AddExtParam(0, 242, 10)"},
            # 5003 deliberately absent from the table (armor references it).
        },
    )

    conn.commit()
    conn.close()
    return db_path


def _build():
    return Build(
        name="測試配裝",
        slots={
            "armor": SlotConfig(
                item_id=2001, refine=10, grade="A", cards=[3001],
                enchants=["Test_Enchant_Str", "Missing_Enchant_XYZ", None],
            ),
            "weapon": SlotConfig(item_id=1001),
            "garment": SlotConfig(item_id=7001),
            # Neither the body item nor the card exist in the DB.
            "shoes": SlotConfig(item_id=9999, cards=[8888]),
        },
    )


def _character():
    return Character(
        name="測試角色", job=4055, base_lv=1, job_lv=1,
        stats={"STR": 10}, traits={}, skills={},
    )


@pytest.fixture
def reader(tmp_path):
    r = DbReader(_setup_db(tmp_path))
    yield r
    r.close()


@pytest.fixture
def effects(reader):
    return evaluate_build(_build(), _character(), reader, EffectMaps(skill_map={63: "測試技能"}))


def test_make_context_scalars_skills_and_slot_maps(reader):
    build = _build()
    character = _character()

    ctx = make_context(character, build, reader)

    assert ctx.scalars == {"base_STR": 10}
    assert ctx.pure_jobs == [4055]
    assert ctx.enabled_skill_levels == {}
    assert ctx.refine_inputs == {
        SLOT_IDS["armor"]: 10, SLOT_IDS["weapon"]: 0, SLOT_IDS["garment"]: 0, SLOT_IDS["shoes"]: 0,
    }
    assert ctx.grade == {
        SLOT_IDS["armor"]: GRADE_LEVELS["A"], SLOT_IDS["weapon"]: 0, SLOT_IDS["garment"]: 0, SLOT_IDS["shoes"]: 0,
    }
    assert ctx.slot_item_id_map == {
        SLOT_IDS["armor"]: 2001, SLOT_IDS["weapon"]: 1001, SLOT_IDS["garment"]: 7001, SLOT_IDS["shoes"]: 9999,
    }


def test_evaluate_build_totals_aggregate_across_item_card_enchant_and_combos(effects):
    # 爆擊傷害 from armor body only.
    assert effects.totals[("爆擊傷害", "%")] == 7.0
    # POW from the enchant.
    assert effects.totals[("POW", "")] == 1.0
    # P.ATK: card(+2) + combo 5001(+5) + combo 6001(+10) = 17; combo 5002
    # never establishes (member 9998 unequipped) so does not contribute.
    assert effects.totals[("P.ATK", "")] == 17.0


def test_evaluate_build_combo_established_names_include_card_member(effects):
    combo_sources = [se.source for se in effects.sourced if se.source.startswith("套裝:")]
    assert "套裝:測試防具+測試卡片" in combo_sources  # 6001: armor+card


def test_evaluate_build_combo_established_from_body_items(effects):
    combo_sources = [se.source for se in effects.sourced if se.source.startswith("套裝:")]
    assert "套裝:測試武器+測試防具" in combo_sources  # 5001: weapon+armor


def test_evaluate_build_combo_not_established_when_member_missing(effects):
    # combo 5002's onstart (AddExtParam(0,242,999)) must never have run.
    assert all(se.entry.value != 999.0 for se in effects.sourced if se.entry.kind == KIND_NUMERIC)


def test_evaluate_build_combo_applied_at_most_once(effects):
    # 5001 is on both weapon and armor's combi_ids; must still fire exactly once.
    combo_sources = [se.source for se in effects.sourced if se.source.startswith("套裝:")]
    assert combo_sources.count("套裝:測試武器+測試防具") == 1
    assert len(combo_sources) == 2  # 5001 + 6001, nothing more


def test_evaluate_build_missing_item_and_card_warn(effects):
    assert "找不到裝備: item_id=9999（部位:shoes）" in effects.warnings
    assert "找不到卡片: item_id=8888（部位:shoes）" in effects.warnings


def test_evaluate_build_missing_enchant_warns(effects):
    assert "找不到詞條: internal_name=Missing_Enchant_XYZ（部位:armor）" in effects.warnings


def test_evaluate_build_missing_combo_warns(effects):
    assert "找不到套裝: combo_id=5003（部位:armor）" in effects.warnings


def test_evaluate_build_unresolved_condition_routed_and_missing_keys_recorded(effects):
    assert len(effects.unresolved) == 1
    unresolved_entry = effects.unresolved[0]
    assert unresolved_entry.entry.kind == KIND_UNRESOLVED
    assert unresolved_entry.slot_key == "garment"
    assert "job_STR" in effects.missing_keys


def test_evaluate_build_enableskill_cross_item_feeds_later_condition(effects):
    # armor's EnableSkill(63,5) runs before weapon's GetSkillLevel(63)
    # condition (SLOT_IDS order: armor before weapon) -> weapon's block
    # resolves instead of becoming unresolved, producing CRI=0.0 (3 // 10).
    assert not any(
        se.entry.kind == KIND_UNRESOLVED and se.slot_key == "weapon" for se in effects.sourced
    )
    assert effects.totals[("CRI", "")] == 0.0
