import re

# `do` is deliberately excluded: it's part of for/while's own syntax
# (`for ... do ... end` / `while ... do ... end`), not a second independent
# opening keyword -- counting it would double-count depth against the
# single `end` that actually closes the for/while.
_KEYWORD_RE = re.compile(r"\b(function|if|for|while|end)\b")


def find_matching_brace(text: str, open_index: int) -> int:
    assert text[open_index] == "{"
    depth = 0
    i = open_index
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            i = _skip_string(text, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"no matching brace for index {open_index}")


def _skip_string(text: str, quote_index: int) -> int:
    quote = text[quote_index]
    i = quote_index + 1
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    raise ValueError(f"unterminated string starting at {quote_index}")


def find_matching_end(text: str, search_from: int) -> int:
    """Find the Lua 'end' keyword matching an opening keyword (if/function/for/while/do).

    Args:
        text: The Lua source text to search
        search_from: Position of the opening keyword (or start position AT the opening keyword).
                    The function assumes search_from points AT an opening keyword position
                    (e.g., the 'i' in 'if' or 'f' in 'function'). The depth counter starts at 1
                    representing that opening keyword, WITHOUT double-counting it.

    Returns:
        The absolute index of the matching 'end' keyword.

    Raises:
        ValueError: If no matching 'end' is found.
    """
    depth = 1
    i = search_from
    n = len(text)
    first_keyword = True
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            i = _skip_string(text, i)
            continue
        m = _KEYWORD_RE.match(text, i)
        if m:
            word = m.group(1)
            if word == "end":
                depth -= 1
                if depth == 0:
                    return i
            else:
                if not first_keyword:
                    depth += 1
                first_keyword = False
            i = m.end()
            continue
        i += 1
    raise ValueError(f"no matching end for search starting at {search_from}")
