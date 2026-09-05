"""缺項(CalcContext.missing_keys)可讀化 — GUI/CLI顯示「未計入」清單用(task-4 brief)。

CalcContext.missing_keys裡的原始字串(如"skill:5015"/"get:200"/"base_STR")對
使用者不友善(要嘛是純數字id, 要嘛是內部欄位命名), 這支函式把它們轉成人類
看得懂的中文描述; 查無對應顯示名的情況一律標明id/欄位名本身(不默默省略),
讓使用者知道是哪個具體項目缺席, 而不是丟一句籠統的「缺資料」。
"""
from typing import Iterable

from app.core.context import GET_FIELD_NAMES


def describe_missing(missing: Iterable[str], skill_map: dict[int, str]) -> list[str]:
    out = []
    for key in missing:
        if key.startswith("skill:"):
            sid = int(key[6:])
            name = skill_map.get(sid)
            out.append(f"技能「{name}」等級" if name else f"技能#{sid}等級")
        elif key.startswith("get:"):
            n = int(key[4:])
            name = GET_FIELD_NAMES.get(n)
            out.append(f"角色欄位 {name}" if name else f"角色欄位 get({n})")
        elif key.startswith("base_"):
            out.append(f"角色素質 {key[5:]}")
        else:
            out.append(key)
    return out
