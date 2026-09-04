"""真實資料端到端驗證 — task-13 brief Step 2.

所有測試需要 data/ro_items.db(真實匯入資料, 20799 items); 不存在時
pytest.skip(這份DB不隨repo提交, 見 .gitignore 的 data/*.db)。

各測試鎖定的真實item(選定原因見task-13-report.md「item選擇+查詢」章節):
- 450263(月全蝕魔力外袍-LT): 本體onstart在 refine13/gradeA/slot2 context下的
  真實計算結果 — MDEF+10、ATK+195(=13*15, 精煉每+1 ATK+15)。
- 5801(新娘的髮帶): 本體onstart含 `if GetSkillLevel(28) == 10 then` 條件,
  角色檔不給技能28時應被路由進 KIND_UNRESOLVED 而非靜默預設。
"""

import inspect
from pathlib import Path

import pytest

import app.cli as cli_module
import app.core.aggregate as aggregate_module
import app.core.compare as compare_module
from app.core.aggregate import evaluate_build
from app.core.build import load_build, load_character
from app.core.context import CalcContext
from app.core.db_reader import DbReader
from app.core.entries import KIND_NUMERIC, KIND_UNRESOLVED
from app.core.maps import make_maps
from app.core.parser import parse_effect_block

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _REPO_ROOT / "data" / "ro_items.db"

pytestmark = pytest.mark.skipif(not _DB_PATH.exists(), reason="需要真實匯入資料 data/ro_items.db(不隨repo提交)")


def _empty_ctx(refine_inputs=None, grade=None, enabled_skill_levels=None) -> CalcContext:
    return CalcContext(
        scalars={},
        refine_inputs=refine_inputs or {},
        grade=grade or {},
        get_values={},
        enabled_skill_levels=enabled_skill_levels or {},
        pure_jobs=[4055],
        slot_item_id_map={},
        weapon_level_map={},
        armor_level_map={},
        weapon_type_map={},
        armor_weapon_map={},
        weapon_atk_map={},
        weapon_matk_map={},
        used_skill_levels={},
    )


def test_450263_base_effects():
    """月全蝕魔力外袍-LT(450263)本體 onstart, refine13/gradeA/slot2 下的真實解析.

    brief 原文的示例(AddDamage_CRI(1,7)→爆擊傷害+7%、AddExtParam(0,242,2)→
    P.ATK+2)對照真實 onstart_equip_src 後查無此二行(該裝備本體完全不含
    AddDamage_CRI / AddExtParam(0,242,...)) — 屬brief示意性寫法與真實資料不符,
    非本測試的裁決依據。改以真實計算結果為準: 描述文字「MDEF+10」與「精煉每+1時
    …ATK+15」在refine=13下對應 MDEF+10、ATK+13*15=195(見report「跟進 1.
    450263」章節的逐行核對)。
    """
    with DbReader(str(_DB_PATH)) as reader:
        item = reader.item(450263)
    assert item is not None
    assert item.onstart_equip_src

    maps = make_maps(str(_DB_PATH))
    ctx = _empty_ctx(refine_inputs={2: 13}, grade={2: 4})
    result = parse_effect_block(item.onstart_equip_src, ctx, 2, maps)

    keys = {(e.key, e.value, e.unit) for e in result.entries if e.kind == KIND_NUMERIC}
    assert ("MDEF", 10.0, "") in keys
    assert ("ATK", 195.0, "") in keys


def test_no_display_string_reparsing():
    """架構鐵則哨兵: aggregate/compare/cli 不得對顯示字串重新做 re.match/
    re.search 解析.

    這幾個模組只應該消費 EffectEntry/BuildEffects 的結構化欄位(key/value/unit/
    kind/category), 不該再對 parser.py 已經產出的顯示字串(如 se.entry.key)
    自己重新用正則去猜語意、或重新推導category — 那類邏輯只能活在 parser.py
    裡(category-taxonomy: 分類改由parser.py handler層直接標註, 顯示字串仍不得
    被下游模組重新解析)。
    """
    for module in (aggregate_module, compare_module, cli_module):
        source = inspect.getsource(module)
        assert "re.match" not in source
        assert "re.search" not in source


def test_classify_category_not_reintroduced():
    """回歸哨兵: classify_category (舊keyword-based分類函式)已整支刪除,
    不得在app/任何原始碼中重新出現 — 分類權威唯一來源是parser.py handler層
    的顯式標註(EXTPARAM_CATEGORY/_stat_category/#1-68逐一標註), 不是關鍵字比對。
    """
    app_root = _REPO_ROOT / "app"
    for py_file in app_root.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        assert "classify_category" not in source, f"classify_category reappeared in {py_file}"


def test_full_build_evaluate_smoke():
    """sample_a(真實450263+波利卡片+INT+5詞條)整套跑通: totals非空, warnings有記錄."""
    build = load_build(_REPO_ROOT / "userdata" / "builds" / "sample_a.json")
    character = load_character(_REPO_ROOT / "userdata" / "characters" / "sample.json")
    maps = make_maps(str(_DB_PATH))

    with DbReader(str(_DB_PATH)) as reader:
        effects = evaluate_build(build, character, reader, maps)

    assert len(effects.totals) > 0
    # ATK/MATK来自裝備本體(精煉13 -> 13*15=195), LUK来自波利卡片, INT来自詞條.
    assert effects.totals[("ATK", "")] == 195.0
    assert effects.totals[("LUK", "")] == 2.0
    assert effects.totals[("INT", "")] == 5.0

    # 真實資料缺口: 波利卡片(4001)combi_ids含combo_id=2000001028, 但combos表
    # 查無此筆(匯入資料本身的缺口, 非本專案bug) — 應被warnings如實記錄而非
    # 靜默吞掉。
    assert isinstance(effects.warnings, list)
    assert "找不到套裝: combo_id=2000001028（部位:armor）" in effects.warnings


def test_unresolved_surface_smoke():
    """5801(新娘的髮帶)含 `if GetSkillLevel(28) == 10 then`, 角色檔無技能28
    時該條件無法判定, 須被路由進 unresolved 而非靜默視為False或True."""
    with DbReader(str(_DB_PATH)) as reader:
        item = reader.item(5801)
    assert item is not None
    assert item.onstart_equip_src
    assert "GetSkillLevel(28)" in item.onstart_equip_src

    maps = make_maps(str(_DB_PATH))
    ctx = _empty_ctx(enabled_skill_levels={})  # 角色檔不給技能28
    result = parse_effect_block(item.onstart_equip_src, ctx, 10, maps)

    unresolved_entries = [e for e in result.entries if e.kind == KIND_UNRESOLVED]
    assert len(unresolved_entries) == 1
    assert "skill:28" in unresolved_entries[0].extra["missing"]
