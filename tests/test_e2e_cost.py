"""真實資料端到端驗證 — task-8 brief Step 2(成本引擎)。

所有測試需要 data/ro_items.db(真實匯入資料); 不存在時 pytest.skip(這份DB不隨
repo提交, 見 .gitignore 的 data/*.db)。跟 test_e2e_effects.py 同一種skip慣例。

這裡是**smoke測試**, 用userdata/裡"活的"rules.json/prices.json/manual_enchants.json
(使用者可能之後會調整), 只斷言結構/正數性質, 不鎖定精確Zeny數字 — 精確數字的
回歸基準屬於task-6的test_cost_report.py(凍結FROZEN_PRICES, 不受userdata/prices.json
變動影響), 這裡不重複那份職責。
"""

from fractions import Fraction
from pathlib import Path

import pytest

from app.core.build import Build, CostTargets, SlotConfig, load_build
from app.core.cost.report import evaluate_build_cost
from app.core.cost.rules import load_prices, load_rules
from app.core.db_reader import DbReader
from app.cli import _load_manual_enchants

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _REPO_ROOT / "data" / "ro_items.db"

pytestmark = pytest.mark.skipif(not _DB_PATH.exists(), reason="需要真實匯入資料 data/ro_items.db(不隨repo提交)")


def _load_live_inputs():
    rules = load_rules(str(_REPO_ROOT / "userdata" / "refine_rules.json"))
    prices = load_prices(str(_REPO_ROOT / "userdata" / "prices.json"))
    manual = _load_manual_enchants(str(_REPO_ROOT / "userdata" / "manual_enchants.json"))
    return rules, prices, manual


def test_sample_a_cost_runs_clean_with_positive_zeny_and_expected_rounds():
    """sample_a(450263, refine0→13, grade none→A, enchant目標slot1
    Star_Cluster_Of_Wis3)用真實DB+活的userdata規則/物價跑evaluate_build_cost
    不拋例外, armor格zeny_total>0(精煉/升階/兌換手續費本身就會遠大於0,
    即使部分材料無價格記為0), 附魔期望輪數(N=1/p)>1(隨機附魔本來就不是
    一次到位, 見report「附魔目標slot1的Wis3權重2000/總權重500000, N=250」)。
    """
    rules, prices, manual = _load_live_inputs()
    build = load_build(_REPO_ROOT / "userdata" / "builds" / "sample_a.json")

    with DbReader(str(_DB_PATH)) as reader:
        report = evaluate_build_cost(build, rules, prices, reader, manual)

        assert len(report.items) == 1
        armor = report.items[0]
        assert armor.slot_key == "armor"
        assert armor.zeny_total > 0
        assert report.zeny_total == armor.zeny_total

        # ItemCostReport不直接暴露expected_rounds(那是enchant.EnchantCostResult
        # 的欄位) — 獨立用solve_enchant對同一個(item, goal)重算一次來斷言N>1,
        # 不靠report層私自推導的中間值。
        from app.core.cost import enchant as enchant_module

        enchant_result = enchant_module.solve_enchant(
            reader, manual, "Lunar_E_Armor_LT", 1, "Star_Cluster_Of_Wis3",
            "last_slot_only", prices,
        )
    assert enchant_result.available
    assert enchant_result.expected_rounds > 1


def test_grade_path_fee_positive():
    """sample_a的armor從grade none升到A(4段升階鏈: none→D→C→B→A, 每段皆有
    NPC升階手續費, 見userdata/refine_rules.json的grade_steps.fee全部>0)—
    grade_fee必須是正值, 不能被精煉手續費(refine_fee, 另一個獨立欄位)吃掉
    或算成0。"""
    rules, prices, manual = _load_live_inputs()
    build = load_build(_REPO_ROOT / "userdata" / "builds" / "sample_a.json")

    with DbReader(str(_DB_PATH)) as reader:
        report = evaluate_build_cost(build, rules, prices, reader, manual)

    armor = report.items[0]
    assert armor.grade_fee > 0


def test_missing_refine_table_warning_propagates_to_build_report():
    """建構一個in-test配裝: 沒有指定refine_table卻要求refine_from(0)→3的
    養成動作(target=3>refine_from) — evaluate_item_cost該產生「未指定精煉表,
    精煉成本略過」警告(report.py _MISSING_REFINE_TABLE_WARNING_FMT), 這裡驗證
    這條警告真的會經evaluate_build_cost彙總後出現在BuildCostReport.warnings裡
    (不只是單一格ItemCostReport.warnings, 是整個配裝彙總層級的傳遞)。用真實
    item_id(450263)確保「查無裝備」警告不會混進來干擾這個斷言。
    """
    rules, prices, manual = _load_live_inputs()
    build = Build(
        name="測試: 缺精煉表",
        slots={
            "armor": SlotConfig(
                item_id=450263, refine=3, grade="none",
                cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table=None),
            ),
        },
    )

    with DbReader(str(_DB_PATH)) as reader:
        report = evaluate_build_cost(build, rules, prices, reader, manual)

    assert "部位armor未指定精煉表, 精煉成本略過" in report.warnings
    assert report.items[0].zeny_total == Fraction(0)
