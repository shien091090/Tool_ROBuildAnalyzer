from app.core.missing_text import describe_missing


def test_describe_missing_kinds():
    out = describe_missing(["skill:5015", "skill:1", "get:200", "get:999", "base_STR", "weird"], {5015: "暴風雪之刃"})
    assert out == ["技能「暴風雪之刃」等級", "技能#1等級", "角色欄位 MHP", "角色欄位 get(999)", "角色素質 STR", "weird"]
