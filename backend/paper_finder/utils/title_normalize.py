import re
from rapidfuzz.fuzz import ratio

_non = re.compile(r'[^a-z0-9 ]+')

def norm_title(s: str) -> str:
    s = (s or "").lower()
    s = _non.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def title_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return ratio(norm_title(a), norm_title(b)) / 100.0
