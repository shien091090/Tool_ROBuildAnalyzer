import re
from typing import Dict

_PAIR_RE = re.compile(r"(\w+)\s*=\s*(-?\d+)")


def parse(text: str) -> Dict[str, int]:
    return {name: int(value) for name, value in _PAIR_RE.findall(text)}
