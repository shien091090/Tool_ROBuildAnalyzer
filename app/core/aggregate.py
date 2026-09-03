"""Single-slot assembly + combo(套裝) detection + whole-build totals — spec §5/§6.

evaluate_build() turns a saved Build + Character into a BuildEffects: every
onstart-equip effect line (item body + cards + enchants + activated combos),
parsed once each, sharing ONE CalcContext so cross-item accumulation
(EnableSkill unlocking a skill level another item's condition then reads,
weapon/armor level maps a later item's GetEquipWeaponLv(GetLocation())-style
condition reads, etc.) works exactly like it does in-client.

Slot processing order (why it matters): app.core.build.SLOT_IDS is defined
with weapon/armor-type slots (armor, weapon, shield, garment, shoes, acc_r,
acc_l, head_top/mid/low) BEFORE shadow and costume slots, specifically so
that any item's "Type=...;Stat={...}" line (which writes
ctx.weapon_level_map/armor_level_map/weapon_type_map for ITS OWN slot) has
already run by the time some OTHER item's onstart condition reads those maps
for a different slot via GetEquipWeaponLv(slot)/GetEquipArmorLv(slot). This
module iterates SLOT_IDS' own insertion order rather than keeping a second,
possibly-drifting list.
"""

from dataclasses import dataclass, field

from app.core.build import GRADE_LEVELS, SLOT_IDS, Build, Character
from app.core.context import CalcContext
from app.core.db_reader import DbReader
from app.core.entries import EffectEntry, KIND_NUMERIC, KIND_UNRESOLVED
from app.core.maps import EffectMaps
from app.core.parser import parse_effect_block


@dataclass(frozen=True)
class SourcedEffect:
    source: str  # 顯示名: 裝備名/卡片名/詞條名/「套裝:X+Y」
    slot_key: str
    entry: EffectEntry


@dataclass
class BuildEffects:
    sourced: list[SourcedEffect]
    totals: dict[tuple[str, str], float]  # (key,unit) -> 加總(僅KIND_NUMERIC)
    unresolved: list[SourcedEffect]  # KIND_UNRESOLVED
    others: list[SourcedEffect]  # DESCRIPTIVE/PROC/UNRECOGNIZED
    warnings: list[str]  # 查無item/卡片/詞條/套裝等(不默默丟)
    missing_keys: set[str] = field(default_factory=set)  # ctx.missing_keys快照


def make_context(character: Character, build: Build, reader: DbReader) -> CalcContext:
    """Build the single CalcContext evaluate_build() shares across the whole build.

    ``reader`` is accepted (not used) to keep this signature symmetric with
    evaluate_build's — kept for future extension (e.g. validating slot item
    ids exist before context construction); nothing here needs a db lookup
    today.
    """
    scalars: dict[str, int] = {}
    for name, value in character.stats.items():
        scalars[f"base_{name}"] = value
    for name, value in character.traits.items():
        scalars[f"base_{name}"] = value

    refine_inputs: dict[int, int] = {}
    grade: dict[int, int] = {}
    slot_item_id_map: dict[int, int] = {}
    for slot_key, cfg in build.slots.items():
        slot_id = SLOT_IDS[slot_key]
        refine_inputs[slot_id] = cfg.refine
        grade[slot_id] = GRADE_LEVELS.get(cfg.grade, 0)
        slot_item_id_map[slot_id] = cfg.item_id

    return CalcContext(
        scalars=scalars,
        refine_inputs=refine_inputs,
        grade=grade,
        get_values={},
        enabled_skill_levels=dict(character.skills),
        pure_jobs=[character.job],
        slot_item_id_map=slot_item_id_map,
        weapon_level_map={},
        armor_level_map={},
        weapon_type_map={},
        armor_weapon_map={},
        weapon_atk_map={},
        weapon_matk_map={},
        used_skill_levels={},
    )


def _parse_and_collect(
    block_text: str | None,
    ctx: CalcContext,
    slot_id: int,
    maps: EffectMaps,
    source: str,
    slot_key: str,
    sourced_out: list[SourcedEffect],
) -> None:
    if not block_text:
        return
    result = parse_effect_block(block_text, ctx, slot_id, maps)
    for entry in result.entries:
        sourced_out.append(SourcedEffect(source=source, slot_key=slot_key, entry=entry))


def evaluate_build(build: Build, character: Character, reader: DbReader, maps: EffectMaps) -> BuildEffects:
    ctx = make_context(character, build, reader)
    sourced: list[SourcedEffect] = []
    warnings: list[str] = []

    # item_id -> (slot_key, slot_id, display_name, combi_ids) for every
    # equipped body-item AND card (spec §6/task-11 brief: combo membership is
    # checked against item_ids INCLUDING cards, not enchants).
    equipped_items: dict[int, tuple[str, int, str, list[int] | None]] = {}
    anchor_order: list[int] = []  # first-seen order, drives combo anchor selection

    for slot_key in SLOT_IDS:
        cfg = build.slots.get(slot_key)
        if cfg is None:
            continue
        slot_id = SLOT_IDS[slot_key]

        item = reader.item(cfg.item_id)
        if item is None:
            warnings.append(f"找不到裝備: item_id={cfg.item_id}（部位:{slot_key}）")
        else:
            display = item.display_name or f"item:{item.item_id}"
            _parse_and_collect(item.onstart_equip_src, ctx, slot_id, maps, display, slot_key, sourced)
            if item.item_id not in equipped_items:
                equipped_items[item.item_id] = (slot_key, slot_id, display, item.combi_ids)
                anchor_order.append(item.item_id)

        for card_id in cfg.cards:
            card = reader.item(card_id)
            if card is None:
                warnings.append(f"找不到卡片: item_id={card_id}（部位:{slot_key}）")
                continue
            display = card.display_name or f"item:{card.item_id}"
            _parse_and_collect(card.onstart_equip_src, ctx, slot_id, maps, display, slot_key, sourced)
            if card.item_id not in equipped_items:
                equipped_items[card.item_id] = (slot_key, slot_id, display, card.combi_ids)
                anchor_order.append(card.item_id)

        for internal_name in cfg.enchants:
            if internal_name is None:
                continue
            enchant = reader.item_by_internal_name(internal_name)
            if enchant is None:
                warnings.append(f"找不到詞條: internal_name={internal_name}（部位:{slot_key}）")
                continue
            display = enchant.display_name or internal_name
            _parse_and_collect(enchant.onstart_equip_src, ctx, slot_id, maps, display, slot_key, sourced)
            # 詞條本身不計入combo成員集合(brief: combo membership只看含卡片的item_ids)

    # ---- 套裝(combo)判定 ----
    # 收集全build已裝備item_id(含卡片), 對每件裝備(依上面同一個固定順序當anchor)
    # 查combi_ids -> combo members是否⊆已裝集合 -> 成立則parse, 每個combo_id最多套用一次.
    equipped_ids = set(equipped_items.keys())
    applied_combo_ids: set[int] = set()
    attempted_combo_ids: set[int] = set()  # 已查詢過(不論成立/查無), 避免重複warning/重複判定

    for item_id in anchor_order:
        slot_key, slot_id, _display, combi_ids = equipped_items[item_id]
        if not combi_ids:
            continue
        for combo_id in combi_ids:
            if combo_id in attempted_combo_ids:
                continue
            attempted_combo_ids.add(combo_id)

            combo = reader.combo(combo_id)
            if combo is None:
                warnings.append(f"找不到套裝: combo_id={combo_id}（部位:{slot_key}）")
                continue

            members, onstart_src = combo
            if not members or not set(members).issubset(equipped_ids):
                continue

            applied_combo_ids.add(combo_id)
            member_names = [equipped_items[m][2] for m in members]
            source = "套裝:" + "+".join(member_names)
            _parse_and_collect(onstart_src, ctx, slot_id, maps, source, slot_key, sourced)

    # ---- 分流: totals(僅NUMERIC加總) / unresolved / others ----
    totals: dict[tuple[str, str], float] = {}
    unresolved: list[SourcedEffect] = []
    others: list[SourcedEffect] = []
    for se in sourced:
        entry = se.entry
        if entry.kind == KIND_NUMERIC:
            key = (entry.key, entry.unit)
            totals[key] = totals.get(key, 0.0) + entry.value
        elif entry.kind == KIND_UNRESOLVED:
            unresolved.append(se)
        else:
            others.append(se)

    return BuildEffects(
        sourced=sourced,
        totals=totals,
        unresolved=unresolved,
        others=others,
        warnings=warnings,
        missing_keys=set(ctx.missing_keys),
    )
