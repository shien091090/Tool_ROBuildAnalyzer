# ROItemSearchApp效果解析器盤點(M2移植依據)

來源: `C:\Users\lithoshu\Desktop\ROItemSearchApp-0.7.17-260816\ro_core.py` 的 `parse_lua_effects_with_variables`(528~2429行)。本文件是M2移植工作的task分解依據, 行號以該版本(0.7.17-260816)為準。

## 函式內部結構總覽

| 區段 | 行號 | 說明 |
|---|---|---|
| 參數/context初始化 | 528-576 | bind_inputs、variables字典組裝(角色素質) |
| regex_cache | 588-622 | 12組正則預編譯(函式屬性快取) |
| 內部輔助函式 | 624-809 | get_grade_value / normalize_lua_expr / _eval_python_expr / safe_eval_expr / eval_condition_expr / split_lua_args / get_lua_call_args / eval_lua_arg / map_int_arg |
| 主迴圈開始 | 811 | for line in lines |
| 逐行前處理 | 812-858 | 去註解、elif→elseif、GetLocation()系列代換(每行都跑, 會寫入context maps預設0) |
| P.S特判 | 863-867 | 不受block_stack閘控 |
| Type+Stat合併行 | 875-887 | 不受閘控 |
| 單行Stat={...} | 892-931 | 不受閘控, 且**無continue**(處理完會繼續往下掉, 靠IGNORE_PREFIXES擋fallback警告 — 移植時保留此控制流避免行為漂移) |
| if/elseif/else/end狀態機 | 936-1010 | block_stack(list of {active, branch_taken}) + condition_met |
| 區塊閘控 | 1013-1014 | 之後所有handler受控 |
| 變數指定handler群 | 1017-1141 | 8個(V1-V8), 寫入函式內variables池 |
| 效果handler長鏈 | 1144-2350 | ~90個匹配點(含11個死碼區塊) |
| Fallback | 2356-2367 | ⛔跳過/🟡無法辨識 |
| skill_delay_accum flush | 2370-2375 | 冷卻累加器收尾輸出 |
| combine_effects/filter_hidden_effects | 2379-2425 | 字串反解聚合+關鍵字遮罩(新架構以結構化聚合取代, 不移植) |

## 輸出格式類型

- (a) 純數值+單位 `{key} {sign}{value}{%|無}` — 約30個
- (b) 秒數型 `... {sign}N.NN 秒` — 2個(固詠/冷卻flush)
- (c) 查表組key型(key由race/element/size/class/skill/unit map組成) — 約33個
- (d) 純文字敘述型 — 約12個(EnableSkill/plain_effect_map的8種/無視防禦類常數/浸透勁)
- (e) P.S原文透傳 — 1個
- (f) 📌變數指定/debug — 8個(V1-V8, 非遊戲效果)
- (g) ✅❌⚠️⛔條件除錯 — 4處來源(if/elseif的✅❌**不受**hide_unrecognized控制)
- (h) 🟡無法辨識fallback — 1個
- (i) 機率/狀態發動型 — Condition()/AddGuideAttack/HP,SPdrain/掉寶率共約4組

**移植決策意涵**: (a)(b)(c)→EffectEntry(key/value/unit); (c)另存{target_kind, target_id}metadata; (d)value=None; (i)extra={chance,duration}; (e)原文欄位; **(f)(g)(h)不進EffectEntry** — (f)(g)分流到trace清單, (h)成為kind=UNRECOGNIZED的結構化條目。

## 效果handler清單(依代碼順序)

### 通用段
| # | 行號 | Lua函式 | 輸出 | 型 |
|---|---|---|---|---|
| 1 | 1149-1158 | EnableSkill(id,lv) | 可使用【skill】Lv.N | d+寫enabled_skill_levels |
| 2 | 1162-1170 | UseSkill(id) | 使用【skill】 | d+寫used_skill_levels |
| 3a | 1178-1200 | (Add\|Sub)ExtParam→CRI/完全迴避 | ÷10 | a |
| 3b | ~1205 | 同→攻擊後延遲類 | 符號反轉,% | a |
| 3c | ~1209 | 同→一般 | effect_map查名, %看名尾 | a |
| 4 | 1217-1229 | (Add\|Sub)SpellDelay | 技能後延遲±N% | a |
| 5 | 1235-1245 | (Add\|Sub)SpellCastTime | 變動詠唱時間±N% | a |
| 6 | 1260-1277 | (Add\|Sub)SFCTEquipAmount(ms) | 固定詠唱時間±N.NN秒(sfct_handled單次鎖) | b |
| 7 | 1279-1297 | (Add\|Sub)SFCTEquipPermill | 固定詠唱時間±N%(÷10, 同鎖) | a |
| 8 | 1311-1323 | (Add\|Sub)Damage_SKID(1,id,e) | 技能【X】傷害(裝備段)±N% | c |
| 9 | 1338-1352 | (Add\|Sub)Damage_passive_SKID | 技能【X】傷害(技能段)±N% | c |
| 10 | 1366-1378 | (Add\|Sub)SkillDelay(id,e) | 累加skill_delay_accum, 延後flush | 副作用 |
| 11 | 1381-1392 | (Add\|Sub)SpecificSpellCastTime | 技能【X】變動詠唱時間±N% | c |
| 12 | 1394-1401 | (Add\|Sub)EXPPercent_KillRace | 從{race}型怪的經驗值±N% | c |
| 13 | 1404-1410 | (Add\|Sub)ReceiveItem_Equip | 掉寶率±N% | a/i |

### 魔法段
| # | 行號 | Lua函式 | 輸出 | 型 |
|---|---|---|---|---|
| 14 | 1427-1434 | (Add\|Sub)SkillMDamage(elem,e) | {element}的魔法傷害±N% | c |
| 15 | 1448-1455 | (Add\|Sub)MDamage_Size(1,s,e) | 對{size}敵人的魔法傷害±N% | c |
| 16 | 1467-1474 | (Add\|Sub)Mdamage_Race | 對{race}型怪的魔法傷害±N% | c |
| 17 | 1488-1495 | (Add\|Sub)MDamage_Property(1,..) | 對{elem}對象的魔法傷害±N% | c |
| 18 | 1508-1516 | (Add\|Sub)Mdamage_Class | 對{class}階級的魔法傷害±N% | c |
| 19 | 1523-1529 | SetIgnoreMdefClass | 無視{class}階級的魔法防禦N% | c |
| 20 | 1536-1542 | SetIgnoreMdefRace | 無視{race}型怪的魔法防禦N% | c |
| 21 | 1549-1556 | (Add\|Sub)Ignore_MRES_RacePercent | 無視{race}型怪的魔法抗性±N% | c |
| 22 | 1562-1567 | MonsterMAtkPercent | 特定魔物魔法增傷+N% | a |
| 23 | 1572-1577 | SubMonsterMAtkPercent | 特定魔物魔法增傷-N% | a |

### 物理段
| # | 行號 | Lua函式 | 輸出 | 型 |
|---|---|---|---|---|
| 24 | 1588-1593 | WeaponMasteryATK | 修煉ATK+N | a |
| 25 | 1596-1601 | Kamui_SpecialATK | 神威ATK+N | a |
| 26 | 1607-1612 | AddGuideAttack | 誘導攻擊機率+N% | a/i |
| 27 | 1623-1629 | (Add\|Sub)Damage_HIT(1,e) | 物理命中傷害±N% | a |
| 28 | 1640-1646 | (Add\|Sub)MeleeAttackDamage(1,e) | 近距離物理傷害±N% | a |
| 29 | 1657-1663 | (Add\|Sub)RangeAttackDamage(1,e) | 遠距離物理傷害±N% | a |
| 30 | 1666-1672 | AddBowAttackDamage(1,e) | 弓攻擊力+N% | a |
| 31 | 1683-1689 | (Add\|Sub)Damage_CRI(1,e) | 爆擊傷害±N% | a |
| 32 | 1702-1710 | (Add\|Sub)Damage_Size(1,s,e) | 對{size}敵人的物理傷害±N% | c |
| 33 | 1721-1728 | Race(Add\|Sub)Damage(r,e) | 對{race}型怪的物理傷害±N% | c |
| 34 | 1741-1748 | (Add\|Sub)Damage_Property(1,el,e) | 對{elem}對象的物理傷害±N% | c |
| 35 | 1762-1769 | Class(Add\|Sub)Damage(c,1,e) | 對{class}階級的物理傷害±N% | c |
| 36 | 1772-1776 | SetIgnoreDEFClass(c) | 無視{class}階級的物理防禦 | d |
| 37 | 1783-1788 | SetIgnoreDefClass_Percent | 無視{class}階級的物理防禦N% | c |
| 38 | 1795-1801 | SetIgnoreDefRace_Percent | 無視{race}型怪的物理防禦N% | c |
| 39 | 1808-1815 | (Add\|Sub)Ignore_RES_RacePercent | 無視{race}型怪的物理抗性±N% | c |
| 40 | 1821-1826 | MonsterAtkPercent | 特定魔物物理增傷+N% | a |
| 41 | 1831-1836 | SubMonsterAtkPercent | 特定魔物物理增傷-N% | a |
| 42 | 1840-1844 | SetIgnoreDEFRace(r) | 無視{race}型怪的物理防禦+100%(常數) | c |
| 43 | 1847-1850 | PerfectDamage(1) | 武器體型修正100%(常數) | d |
| 44 | 1852-1857 | SetInvestigate() | 浸透勁+全種族無視物防100%(兩條)。**原正則`r"SetInvestigate()"`的()是空群組, 等同前綴比對 — 移植時修為`\(\s*\)`並註記** | d |

### 補完解析段
| # | 行號 | Lua函式 | 輸出 | 型 |
|---|---|---|---|---|
| 45 | 1887-1893 | (Add\|Sub)HealValue | 治癒量±N% | a |
| 46 | 1898-1904 | (Add\|Sub)HealModifyPercent | 被治癒量±N% | a |
| 47a | 1911-1922 | (Add\|Sub)(HP\|SP)drain(rate) | {pool}吸收±N% | a/i |
| 47b | 同 | 雙參(rate,amount) | 吸收機率+吸收量兩條 | a/i |
| 48 | 1928-1934 | (Add\|Sub)SPconsumption | SP消耗±N% | a |
| 49 | 1938-1950 | (add\|sub)spconsumption(v,id)(小寫) | 技能【X】SP消耗±N% | c |
| 50 | 1955-1967 | (Add\|Sub)SkillSP(id,v) | 技能【X】SP消耗±N | c |
| 51 | 1978-1984 | (Add\|Sub)MeleeAttackDamage(0,e) | 受到近距離物理傷害±N% | a |
| 52 | 1995-2001 | (Add\|Sub)RangeAttackDamage(0,e) | 受到遠距離物理傷害±N% | a |
| 53 | 2007-2015 | (Add\|Sub)AttrTolerace(el,v) | 對{elem}攻擊抗性±N% | c |
| 54 | 2020-2028 | (add\|sub)attrtolerace(小寫同義) | 同上 | c |
| 55 | 2031-2038 | (Add\|Sub)Damage_Size(0,s,e) | 受到{size}敵人的物理傷害±N% | c |
| 56 | 2041-2048 | (Add\|Sub)MDamage_Size(0,s,e) | 受到{size}敵人的魔法傷害±N% | c |
| 57 | 2053-2062 | (Add\|Sub)RaceTolerace(r,v) | 受到{race}型怪的傷害±N% **符號反轉: Add=承傷下降** | c |
| 58 | 2075-2082 | (Add\|Sub)Damage_Property(0,el,e) | 受到{elem}對象的物理傷害±N% | c |
| 59 | 2096-2103 | (Add\|Sub)MDamage_Property(0,el,e) | 受到{elem}對象的魔法傷害±N% | c |
| 60 | 2107-2114 | Class(Add\|Sub)Damage(c,0,e) | 受到{class}階級的物理傷害±N% | c |
| 61 | 2119-2127 | Race(Sub\|Add)DamageSelf(r,v) | 受到{race}型怪的傷害±N% | c |
| 62 | 2184-2192 | (Add\|Sub)CRIPercent_Race(r,v) | 對{race}型怪的CRI±N% | c |
| 63 | 2197-2203 | (Add\|Sub)MeleeAttackReflect | 近距離物理反射±N% | a |
| 64 | 2207-2213 | (Add\|Sub)ReflectMagic | 魔法反射±N% | a |
| 65 | 2217-2223 | (Add\|Sub)ReflectTolerace | 反射傷害耐性±N% | a |
| 66 | 2237-2249 | (Add\|Sub)Damage_SKID(0,id,e) | 受到技能【X】傷害±N% | c |
| 67 | 2317-2320 | plain_effect_map 8種無參數旗標(NoDispell/Magicimmune/NoJamstone/NoMadogearfuel/AddNeverknockback/Clairvoyance/Reincarnation/SplashAttack) | 固定敘述句 | d |
| 68 | 2328-2350 | Condition(status_id,dur,chance) | 賦予狀態:{status}(持續d, 機率c%), status_map只認5種ID(13/14/15/21/26) | i |

### 死碼(整段註解, 不移植)
2129-2140, 2142-2152, 2154-2163, 2165-2171, 2174-2179, 2251-2256, 2258-2263, 2265-2269, 2271-2276, 2278-2286, 2288-2296(AttackedWeaponPower系列/Reset系列/SubBowAttackDamage/SubGuideAttack)

## 變數指定handler(V1-V8, 1017-1141)
V1多段GetRefineLevel連加 / V2 GetRefineLevel / V3 GetEquipGradeLevel / V4 GetEquipArmorLv / V5 GetWeaponClass / V6 GetEquipWeaponLv / V7 math.floor / V8一般算式(字串/`{`/function跳過)。全部寫入函式內variables池供後續行運算, 不產生效果條目。

## 查表依賴
- dependencies.require系(7張): race_map(11次)/skill_map(8)/element_map(7)/class_map(6)/stat_name_sets(2)/weapon_type_map(1, 與context.weapon_type_map**同名異義**)/excluded_stat_names(1)
- 函式直接參數(3張): unit_map/size_map/effect_map — **管道不一致, 移植時統一**
- 靜態表定義位置: ItemSearchApp.py 2100-2249(effect_map/element_map/size_map/race_map/unit_map/class_map/stat_name_sets/weapon_type_map/excluded_stat_names), ro_core.py 2307(plain_effect_map)/2328附近(status_map)
- skill_map: ItemSearchApp.py 2674起執行時從csv載入 — 新專案改走importer的skills表(client GRF的SkillInfoZ)
- dependencies.register_function共89次呼叫 = 死碼(function_defs全檔無讀取點), **不移植**

## context讀取點
- 純量65個: target_element / skill_focus_AGI / skill_focus_DEX / total_AGI / total_DEX + 12素質x5前綴(base_/job_/equip_/base_equip_/total_)
- 可變map: weapon_level_map(讀寫)/armor_level_map(讀寫)/weapon_type_map(讀寫)/armor_weapon_map(只寫)/weapon_atk_map(只寫)/weapon_matk_map(只寫)/slot_item_id_map(只讀)/enabled_skill_levels(讀寫)/used_skill_levels(只寫)/pure_jobs(只讀)
- 參數層: get_values(Lua的get(N))/refine_inputs/grade(int或dict, **GetPetRelationship()共用grade值來源** — 語意怪異但照搬並註記)/current_location_slot
- 原始碼一律context.get(key,0)吃預設, **不會告訴你缺什麼** — 新專案的miss偵測要自建必填清單

## 狀態副作用清單
1. 每行前處理(825-852): current_location_slot的三張map缺key就寫0(隱性初始化)
2. Stat行(892-931): 寫6張map, 且無continue
3. Type+Stat行(875-887): **不寫**任何map(與Stat行不一致, 疑似既有bug, 照搬並註記)
4. V1-V8: 寫variables池
5. EnableSkill/UseSkill: 寫context
6. AddSkillDelay: skill_delay_accum延後flush(唯一延後聚合器)
7. SetInvestigate寫used_skill_levels[266]已被原作者註解掉(移到計算層), 不要加回

## Fallback行為(2356-2367)
IGNORE_PREFIXES=("local ","Stat ","{Type ","}"), hide_unrecognized=True時未匹配行完全靜默丟棄; False時: 條件不成立→⛔, IGNORE前綴→跳過, 其餘→🟡原文透傳。新架構改為kind=UNRECOGNIZED結構化條目(不默默丟資料)。

## 下游字串依賴(不移植, 以結構化取代)
combine_effects(2386-2404)用正則反解自家輸出字串做(key,suffix)加總; filter_hidden_effects(2406-2425)用關鍵字判物理/魔法。新架構: 聚合直接groupby EffectEntry(key,unit); category在條目生成當下標記。
