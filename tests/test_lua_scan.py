from importer.lua_scan import find_matching_brace, find_matching_end


def test_find_matching_brace_simple():
    text = "{a, b}"
    assert find_matching_brace(text, 0) == 5


def test_find_matching_brace_nested():
    text = "{a, {b, c}, d}"
    assert find_matching_brace(text, 0) == 13


def test_find_matching_brace_ignores_braces_in_string():
    text = '{a = "}}}", b = 1}'
    assert find_matching_brace(text, 0) == len(text) - 1


def test_find_matching_brace_handles_escaped_quote_in_string():
    text = r'{a = "he said \"hi\"", b = "}"}'
    assert find_matching_brace(text, 0) == len(text) - 1


def test_find_matching_end_simple_if():
    text = "if x > 5 then y = 1 end"
    idx = find_matching_end(text, 0)
    assert text[idx:idx + 3] == "end"


def test_find_matching_end_nested_if_and_function():
    text = (
        "function()\n"
        "  local temp = 0\n"
        "  if GetRefineLevel(3) > 5 then\n"
        "    temp = (GetRefineLevel(3) - 5) * 2\n"
        "  end\n"
        "  AddDamage_SKID(1, 2310, 20 + temp)\n"
        "end"
    )
    idx = find_matching_end(text, 0)
    assert idx == len(text) - 3


def test_find_matching_end_ignores_keyword_in_string():
    text = 'function()\n  SetCaution("end of message")\nend'
    idx = find_matching_end(text, 0)
    assert idx == len(text) - 3


def test_find_matching_end_handles_elseif():
    """Regression test: word boundary must not break on 'if' inside 'elseif'."""
    text = "if a then\n x=1\nelseif b then\n x=2\nend"
    idx = find_matching_end(text, 0)
    assert text[idx:idx + 3] == "end"
    assert idx == len(text) - 3


def test_find_matching_end_handles_for_loop_with_do():
    # `do` is part of for's own syntax (for ... do ... end), not a second
    # opening keyword -- must not be double-counted against the single `end`.
    text = "for i = 1, 10 do\n  x = x + i\nend"
    idx = find_matching_end(text, 0)
    assert idx == len(text) - 3


def test_find_matching_end_handles_while_loop_with_do():
    text = "while x < 10 do\n  x = x + 1\nend"
    idx = find_matching_end(text, 0)
    assert idx == len(text) - 3


def test_find_matching_end_for_loop_nested_inside_if():
    text = (
        "if cond then\n"
        "  for i = 1, 10 do\n"
        "    x = x + i\n"
        "  end\n"
        "end"
    )
    idx = find_matching_end(text, 0)
    assert idx == len(text) - 3


def test_find_matching_end_identifier_ending_in_keyword():
    """Regression test: must not match 'end' inside identifier like 'append'."""
    text = "function()\n  append(x)\nend"
    idx = find_matching_end(text, 0)
    # The real 'end' is at the very end, not inside 'append'
    assert idx == len(text) - 3
    assert text[idx:idx + 3] == "end"
