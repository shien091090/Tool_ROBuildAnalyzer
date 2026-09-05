"""AnalyzerSession — GUI唯一資料入口: 開一次DB/maps/catalog/rules/prices/manual, 封裝評估/比較/成本/附魔池/檔案列舉。

M4 GUI(task5~8)不得直接碰DbReader/CostRules/ItemCatalog等底層物件 — 一律
透過這個class的方法; 這裡本身不做任何解析/顯示排版邏輯(那些各自留在
build.py/aggregate.py/cost/*.py/missing_text.py), 只是把「開一次資源、
組合呼叫既有函式」的orchestration集中起來, 避免GUI每個畫面各自重複
初始化DbReader/EffectMaps/ItemCatalog造成多個db連線或多份重複載入的規則檔。
"""
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from app.core.aggregate import BuildEffects, evaluate_build
from app.core.build import Build, Character, load_build, load_character, save_build
from app.core.catalog import ItemCatalog
from app.core.compare import CompareRow, compare_builds
from app.core.cost.enchant import rows_for_item
from app.core.cost.report import BuildCostReport, evaluate_build_cost
from app.core.cost.rules import CostRules, load_prices, load_rules
from app.core.db_reader import DbReader
from app.core.maps import EffectMaps, make_maps
from app.core.missing_text import describe_missing
from importer.config import ConfigInvalidError, ConfigNotFoundError
from importer.config import load as load_config


def resolve_db_path(config_path: str = "config.json") -> str:
    """config.json 的 db_path 欄位(不存在/不合法時退回預設 data/ro_items.db).

    從app/cli.py搬過來(task-4 brief) — cli.py改成從這裡import, 行為不變。
    """
    try:
        return load_config(config_path).db_path
    except (ConfigNotFoundError, ConfigInvalidError):
        return "data/ro_items.db"


@dataclass(frozen=True)
class EnchantOption:
    option_internal_name: str
    display_name: str
    weight: int
    probability: Fraction
    description: str


@dataclass(frozen=True)
class EnchantSlotPool:
    slot_index: int
    options: tuple[EnchantOption, ...]


class AnalyzerSession:
    def __init__(self, db_path, *, rules_path="userdata/refine_rules.json", prices_path="userdata/prices.json",
                 manual_path="userdata/manual_enchants.json", builds_dir="userdata/builds",
                 characters_dir="userdata/characters"):
        self.db_path = db_path
        self.reader = DbReader(db_path)
        self.maps: EffectMaps = make_maps(db_path)
        self.catalog = ItemCatalog.from_reader(self.reader)
        self.rules: CostRules = load_rules(rules_path)
        self.prices: dict[str, int] = load_prices(prices_path)
        self.manual: dict = json.loads(Path(manual_path).read_text(encoding="utf-8"))
        self.builds_dir = Path(builds_dir)
        self.characters_dir = Path(characters_dir)

    @classmethod
    def from_config(cls, config_path="config.json"):
        return cls(resolve_db_path(config_path))

    def close(self):
        self.reader.close()

    def import_date(self):
        return self.reader.meta("import_date")

    def list_builds(self):
        return sorted(self.builds_dir.glob("*.json")) if self.builds_dir.exists() else []

    def list_characters(self):
        return sorted(self.characters_dir.glob("*.json")) if self.characters_dir.exists() else []

    def load_build(self, path):
        return load_build(path)

    def save_build(self, build, path):
        save_build(build, path)

    def load_character(self, path):
        return load_character(path)

    def evaluate(self, build: Build, character: Character) -> BuildEffects:
        return evaluate_build(build, character, self.reader, self.maps)

    def compare(self, a, b) -> list[CompareRow]:
        return compare_builds(a, b)

    def cost(self, build: Build) -> BuildCostReport:
        return evaluate_build_cost(build, self.rules, self.prices, self.reader, self.manual)

    def enchant_pools(self, item_id: int) -> list[EnchantSlotPool]:
        entry = self.catalog.get(item_id)
        if entry is None or not entry.internal_name:
            return []
        found = rows_for_item(self.reader, self.manual, entry.internal_name)
        if found is None:
            return []
        _table_key, rows = found  # rows: (slot_index, require_cost, option_internal_name, option_weight)
        by_slot: dict[int, dict[str, int]] = {}
        for slot_index, _rc, option, weight in rows:
            slot = by_slot.setdefault(slot_index, {})
            slot[option] = slot.get(option, 0) + weight  # 重複列權重相加=與spec §7.5分母一致
        pools = []
        for slot_index in sorted(by_slot, reverse=True):
            total = sum(by_slot[slot_index].values())
            options = []
            for option, weight in sorted(by_slot[slot_index].items(), key=lambda kv: (-kv[1], kv[0])):
                rec = self.reader.item_by_internal_name(option)
                display = rec.display_name if rec and rec.display_name else option
                options.append(EnchantOption(option, display, weight,
                                             Fraction(weight, total) if total else Fraction(0),
                                             rec.description if rec else ""))
            pools.append(EnchantSlotPool(slot_index, tuple(options)))
        return pools

    def refine_table_choices(self):
        return sorted((k, self.rules.table_displays.get(k, k)) for k in self.rules.refine_tables)

    def item_display(self, item_id):
        e = self.catalog.get(item_id)
        return e.display_name if e else f"item:{item_id}"

    def option_display(self, internal_name):
        rec = self.reader.item_by_internal_name(internal_name)
        return rec.display_name if rec and rec.display_name else internal_name

    def describe_missing(self, missing):
        return describe_missing(missing, self.maps.skill_map)

    def active_combo_members(self, build: Build, item_id: int) -> set[int]:
        """item_id所屬、且成員全在build已裝(本體+卡片)的所有combo成員id聯集(GUI hover套裝高亮用)。

        查無該item/該item沒有combi_ids/成員未全裝滿 → set()(不成立, 不高亮)。
        """
        equipped = set()
        for cfg in build.slots.values():
            equipped.add(cfg.item_id)
            equipped.update(cfg.cards)
        rec = self.reader.item(item_id)
        if rec is None or not rec.combi_ids:
            return set()
        members_all: set[int] = set()
        for combo_id in rec.combi_ids:
            combo = self.reader.combo(combo_id)
            if combo is None:
                continue
            members, _src = combo
            if members and set(members).issubset(equipped):
                members_all.update(members)
        return members_all
