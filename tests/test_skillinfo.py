from importer.parsers.skillinfo import parse_skillid, parse_skillinfolist, parse_skilldescript, merge_skills

SKILLID_SAMPLE = (
    'SKID = {NV_BASIC = 1, SM_SWORD = 2, SM_TWOHAND = 3, '
    'SR_KNUCKLEARROW = 2336, SR_LIGHTNINGWALK = 2335}'
)


def test_parse_skillid():
    result = parse_skillid(SKILLID_SAMPLE)
    assert result == {
        "NV_BASIC": 1,
        "SM_SWORD": 2,
        "SM_TWOHAND": 3,
        "SR_KNUCKLEARROW": 2336,
        "SR_LIGHTNINGWALK": 2335,
    }


# Real production data (2026-08-27, decompiled from SkillInfoZ/skillinfolist.lub),
# shortened to two entries -- one plain, one with the optional Type field.
SKILLINFOLIST_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.SR_KNUCKLEARROW] = {"SR_KNUCKLEARROW"; SkillName = "拳刃箭矢", MaxLv = 10, \n'
    'SpAmount = {12, 14, 16, 18, 20, 22, 24, 26, 28, 30}, bSeperateLv = false, \n'
    'AttackRange = {7, 7, 8, 8, 9, 9, 10, 10, 11, 11}, \n'
    '_NeedSkillList = {\n'
    '{SKID.SR_LIGHTNINGWALK, 1}}}, \n'
    '[SKID.AC_MAKINGARROW] = {"AC_MAKINGARROW"; SkillName = "製作箭", MaxLv = 1, Type = "Quest", \n'
    'SpAmount = {10}, bSeperateLv = false, \n'
    'AttackRange = {1}}, \n'
    '}'
)


# Real production data (2026-08-27): a skill with ApAmount (only some
# fourth-job-era skills have this second resource cost).
SKILLINFOLIST_AP_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.DK_DRAGONIC_AURA] = {"DK_DRAGONIC_AURA"; SkillName = "龍神氣息", MaxLv = 10, \n'
    'SpAmount = {100, 100, 100, 100, 100, 100, 100, 100, 100, 100}, \n'
    'ApAmount = {150, 150, 150, 150, 150, 150, 150, 150, 150, 150}, bSeperateLv = true, \n'
    'AttackRange = {7, 7, 7, 7, 7, 7, 7, 7, 7, 7}}, \n'
    '}'
)


def test_parse_skillinfolist_number_arrays():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)

    assert result["SR_KNUCKLEARROW"]["sp_amount"] == [12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
    assert result["SR_KNUCKLEARROW"]["attack_range"] == [7, 7, 8, 8, 9, 9, 10, 10, 11, 11]
    assert result["SR_KNUCKLEARROW"]["ap_amount"] is None

    assert result["AC_MAKINGARROW"]["sp_amount"] == [10]
    assert result["AC_MAKINGARROW"]["attack_range"] == [1]


def test_parse_skillinfolist_ap_amount_present():
    result, _ = parse_skillinfolist(SKILLINFOLIST_AP_SAMPLE)
    assert result["DK_DRAGONIC_AURA"]["ap_amount"] == [150] * 10


# Real production data (2026-08-27, shortened to 3 levels): an AOE skill
# with per-level SkillScale (x,y range), unlike ordinary skills.
SKILLINFOLIST_SCALE_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.NPC_EARTHQUAKE_K] = {"NPC_EARTHQUAKE_K"; SkillName = "地震術", MaxLv = 3, \n'
    'SpAmount = {0, 0, 0}, bSeperateLv = false, \n'
    'AttackRange = {1, 1, 1}, \n'
    'SkillScale = {\n'
    '[1] = {x = 11, y = 11}, \n'
    '[2] = {x = 15, y = 15}, \n'
    '[3] = {x = 19, y = 19}}}, \n'
    '}'
)


def test_parse_skillinfolist_skill_scale_present():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SCALE_SAMPLE)
    assert result["NPC_EARTHQUAKE_K"]["skill_scale"] == [
        {"x": 11, "y": 11},
        {"x": 15, "y": 15},
        {"x": 19, "y": 19},
    ]


def test_parse_skillinfolist_skill_scale_absent_is_none():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    assert result["SR_KNUCKLEARROW"]["skill_scale"] is None


# Real production data (2026-08-27): a skill with multiple base
# prerequisites (all from different, unrelated job trees).
SKILLINFOLIST_MULTI_PREREQ_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.LK_HEADCRUSH] = {"LK_HEADCRUSH"; SkillName = "破頭蓋", MaxLv = 5, \n'
    'SpAmount = {10, 10, 10, 10, 10}, bSeperateLv = false, \n'
    'AttackRange = {1, 1, 1, 1, 1}, \n'
    '_NeedSkillList = {\n'
    '{SKID.SM_BASH, 10}, \n'
    '{SKID.KN_SPEARMASTERY, 5}, \n'
    '{SKID.KN_RIDING, 1}}}, \n'
    '}'
)


def test_parse_skillinfolist_base_prerequisites_single():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    assert result["SR_KNUCKLEARROW"]["base_prerequisites"] == [
        {"skill": "SR_LIGHTNINGWALK", "level": 1},
    ]


def test_parse_skillinfolist_base_prerequisites_absent_is_none():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    assert result["AC_MAKINGARROW"]["base_prerequisites"] is None


def test_parse_skillinfolist_base_prerequisites_multiple():
    result, _ = parse_skillinfolist(SKILLINFOLIST_MULTI_PREREQ_SAMPLE)
    assert result["LK_HEADCRUSH"]["base_prerequisites"] == [
        {"skill": "SM_BASH", "level": 10},
        {"skill": "KN_SPEARMASTERY", "level": 5},
        {"skill": "KN_RIDING", "level": 1},
    ]


# Real production data (2026-08-27, shortened): a skill with job-specific
# extra prerequisites keyed by JOBID -- different job trees converging on
# the same skill need different things.
SKILLINFOLIST_JOB_PREREQ_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.CG_MOONLIT] = {"CG_MOONLIT"; SkillName = "月光", MaxLv = 5, \n'
    'SpAmount = {30, 40, 50, 60, 70}, bSeperateLv = true, \n'
    'AttackRange = {1, 1, 1, 1, 1}, \n'
    'NeedSkillList = {\n'
    '[JOBID.JT_BARD_H] = {\n'
    '{SKID.AC_CONCENTRATION, 5}, \n'
    '{SKID.BA_MUSICALLESSON, 7}}, \n'
    '[JOBID.JT_DANCER_H] = {\n'
    '{SKID.AC_CONCENTRATION, 5}, \n'
    '{SKID.DC_MUSICALLESSON, 7}}}}, \n'
    '}'
)

# Real production data (2026-08-27, item AL_CURE): both base_prerequisites
# AND job_prerequisites present at once on the same skill.
SKILLINFOLIST_BOTH_PREREQ_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.AL_CURE] = {"AL_CURE"; SkillName = "治癒術", MaxLv = 1, \n'
    'SpAmount = {15}, bSeperateLv = false, \n'
    'AttackRange = {9}, \n'
    '_NeedSkillList = {\n'
    '{SKID.AL_HEAL, 2}}, \n'
    'NeedSkillList = {\n'
    '[JOBID.JT_CRUSADER] = {\n'
    '{SKID.CR_TRUST, 5}}}}, \n'
    '}'
)


def test_parse_skillinfolist_job_prerequisites():
    result, _ = parse_skillinfolist(SKILLINFOLIST_JOB_PREREQ_SAMPLE)
    assert result["CG_MOONLIT"]["job_prerequisites"] == {
        "JT_BARD_H": [
            {"skill": "AC_CONCENTRATION", "level": 5},
            {"skill": "BA_MUSICALLESSON", "level": 7},
        ],
        "JT_DANCER_H": [
            {"skill": "AC_CONCENTRATION", "level": 5},
            {"skill": "DC_MUSICALLESSON", "level": 7},
        ],
    }


def test_parse_skillinfolist_job_prerequisites_absent_is_none():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    assert result["SR_KNUCKLEARROW"]["job_prerequisites"] is None


def test_parse_skillinfolist_base_and_job_prerequisites_coexist():
    result, _ = parse_skillinfolist(SKILLINFOLIST_BOTH_PREREQ_SAMPLE)
    assert result["AL_CURE"]["base_prerequisites"] == [
        {"skill": "AL_HEAL", "level": 2},
    ]
    assert result["AL_CURE"]["job_prerequisites"] == {
        "JT_CRUSADER": [{"skill": "CR_TRUST", "level": 5}],
    }


# Real production data (2026-08-27, shortened): skilldescript.lub is a
# plain array of quoted strings per skill, same shape as items'
# description_lines.
SKILLDESCRIPT_SAMPLE = (
    '[SKID.SR_WINDMILL] = {"自轉風車", "MAX Lv : 1", '
    '"^777777習得條件 : 覺醒1 ^000000", "系列 : ^777777主動/傷害 ^000000"}, \n'
    '[SKID.SR_ASSIMILATEPOWER] = {"融合力", "MAX Lv : 1"}, \n'
)


def test_merge_skills_combines_all_three_sources():
    skillid_map = {"SR_KNUCKLEARROW": 2336, "SR_LIGHTNINGWALK": 2335}
    info_map, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    desc_map = {"SR_KNUCKLEARROW": ["修羅身彈", "MAX Lv : 10"]}

    rows = merge_skills(skillid_map, info_map, desc_map)
    row = next(r for r in rows if r["internal_name"] == "SR_KNUCKLEARROW")

    assert row["skill_id"] == 2336
    assert row["skill_name"] == "拳刃箭矢"
    assert row["max_level"] == 10
    assert row["description_lines"] == ["修羅身彈", "MAX Lv : 10"]
    # base_prerequisites' internal names are resolved to real skill_ids here.
    assert row["base_prerequisites"] == [{"skill_id": 2335, "level": 1}]


def test_merge_skills_missing_description_is_empty_list():
    skillid_map = {"AC_MAKINGARROW": 43}
    info_map, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    desc_map = {}  # no description at all for this skill

    rows = merge_skills(skillid_map, info_map, desc_map)
    row = next(r for r in rows if r["internal_name"] == "AC_MAKINGARROW")
    assert row["description_lines"] == []


def test_merge_skills_job_prerequisites_resolved_to_skill_ids():
    skillid_map = {
        "CG_MOONLIT": 500, "AC_CONCENTRATION": 45, "BA_MUSICALLESSON": 46,
        "DC_MUSICALLESSON": 47,
    }
    info_map, _ = parse_skillinfolist(SKILLINFOLIST_JOB_PREREQ_SAMPLE)
    rows = merge_skills(skillid_map, info_map, {})
    row = next(r for r in rows if r["internal_name"] == "CG_MOONLIT")
    assert row["job_prerequisites"] == {
        "JT_BARD_H": [{"skill_id": 45, "level": 5}, {"skill_id": 46, "level": 7}],
        "JT_DANCER_H": [{"skill_id": 45, "level": 5}, {"skill_id": 47, "level": 7}],
    }


def test_merge_skills_skips_entries_with_no_known_skill_id():
    # SR_KNUCKLEARROW is in info_map but NOT in skillid_map -- can't build a
    # row without a real skill_id (the table's primary key), so it must be
    # excluded rather than inserted with a bogus/null id.
    skillid_map = {}
    info_map, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)
    rows = merge_skills(skillid_map, info_map, {})
    assert rows == []


def test_parse_skilldescript():
    result = parse_skilldescript(SKILLDESCRIPT_SAMPLE)
    assert result["SR_WINDMILL"] == [
        "自轉風車", "MAX Lv : 1",
        "^777777習得條件 : 覺醒1 ^000000", "系列 : ^777777主動/傷害 ^000000",
    ]
    assert result["SR_ASSIMILATEPOWER"] == ["融合力", "MAX Lv : 1"]


# Real production data shape (2026-08-28, item DA_TIMEOUT/ALL_TIMEIN):
# DA_TIMEOUT's decompiled SkillName string never closes at the intended
# spot and instead swallows all of the next entry's opening syntax up to
# that entry's own first quote. Neither skill's fields can be safely
# recovered from this -- DA_TIMEOUT's fields are contaminated with
# ALL_TIMEIN's, and ALL_TIMEIN never gets its own entry match at all.
#
# The swallowed span in real data is LITERAL backslash-n/backslash-t text
# (two characters each: "\" + "n"), not real newline/tab control
# characters -- this is exactly why _ENTRY_START_RE's \s* never matches
# across it in production (a literal "\" isn't whitespace), so
# ALL_TIMEIN's "[SKID.ALL_TIMEIN] = {" text is never mistaken for a real
# entry boundary. Using "\\n"/"\\t" (double-escaped) below reproduces that
# real byte shape instead of accidentally using actual control characters.
SKILLINFOLIST_CORRUPTED_SAMPLE = (
    'SKILL_INFO_LIST = {\n'
    '[SKID.DA_TIMEOUT] = {"DA_TIMEOUT"; SkillName = "Timeout], '
    '\\n\\t\\tMaxLv = 3, \\n\\t\\tSpAmount = { 500, 300, 100, }, '
    '\\n\\t\\tbSeperateLv = false, \\n\\t\\tAttackRange = { 9, 9, 9, }, '
    '\\n\\t}, \\n\\n\\t[SKID.ALL_TIMEIN] = \\n\\t'
    '{\\n\\t\\t[=[ALL_TIMEIN", SkillName = "Learn", MaxLv = 1, \n'
    'SpAmount = {100}, bSeperateLv = false, \n'
    'AttackRange = {1}}, \n'
    '[SKID.DA_ZENYRANK] = {"DA_ZENYRANK"; SkillName = "Rank", MaxLv = 1, \n'
    'SpAmount = {10}, bSeperateLv = false, \n'
    'AttackRange = {1}}, \n'
    '}'
)


def test_parse_skillinfolist_skips_corrupted_entry_with_swallowed_next_entry():
    info_map, corrupted_count = parse_skillinfolist(SKILLINFOLIST_CORRUPTED_SAMPLE)
    # DA_TIMEOUT's own fields are contaminated -- must not be recorded at all.
    assert "DA_TIMEOUT" not in info_map
    # ALL_TIMEIN never had its own regex-matched entry to begin with (its
    # opening syntax got swallowed) -- also correctly absent.
    assert "ALL_TIMEIN" not in info_map
    # The skill AFTER the corrupted pair must still parse fine -- corruption
    # must not cascade past the entry that actually closes cleanly.
    assert "DA_ZENYRANK" in info_map
    assert info_map["DA_ZENYRANK"]["skill_name"] == "Rank"
    assert corrupted_count == 1


def test_parse_skillinfolist_basic_fields():
    result, _ = parse_skillinfolist(SKILLINFOLIST_SAMPLE)

    assert result["SR_KNUCKLEARROW"]["skill_name"] == "拳刃箭矢"
    assert result["SR_KNUCKLEARROW"]["max_level"] == 10
    assert result["SR_KNUCKLEARROW"]["skill_type"] is None
    assert result["SR_KNUCKLEARROW"]["is_level_select"] is False

    assert result["AC_MAKINGARROW"]["skill_name"] == "製作箭"
    assert result["AC_MAKINGARROW"]["max_level"] == 1
    assert result["AC_MAKINGARROW"]["skill_type"] == "Quest"
    assert result["AC_MAKINGARROW"]["is_level_select"] is False
