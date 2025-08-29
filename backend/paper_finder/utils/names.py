# paper_finder/utils/names.py
from __future__ import annotations
import re
from typing import Iterable, List, Tuple, Dict, Set, Optional

# 尝试使用 pypinyin（可选）
try:
    from pypinyin import pinyin, Style
except Exception:  # 未安装时降级
    pinyin = None
    Style = None


_SPACES = re.compile(r"\s+")
_PUNCS = re.compile(r"[·\u00B7\.\-_,;/]+")


def normalize_name(s: str) -> str:
    """
    统一大小写与分隔符，用于无损（可读）比较：保留空格，但清洗标点与多余空格。
    """
    s = (s or "").strip()
    s = _PUNCS.sub(" ", s)
    s = _SPACES.sub(" ", s)
    return s.lower()


def compact_token(s: str) -> str:
    """
    强归一 token（用于强对齐、去重 key）：仅保留字母数字。
    """
    return re.sub(r"[^a-z0-9]", "", normalize_name(s))


def cn_to_pinyin_space(cn_name: str) -> Optional[str]:
    """
    中文 → 空格分隔拼音（Zhang Xi）。未安装 pypinyin 时返回 None。
    """
    if not cn_name or pinyin is None:
        return None
    syls = pinyin(cn_name, style=Style.NORMAL, strict=False)
    # 扁平 + 首字母大写
    parts = [w[0] for w in syls if w and w[0]]
    parts = [part.capitalize() for part in parts if part.strip()]
    # 简单合并姓氏规则：若长度>=2 且首个 token 可能是复姓（此处不做过度智能）
    return " ".join(parts).strip() or None


def _abbr_token(tok: str) -> str:
    # Xi -> X. / X
    t = (tok or "").strip()
    return f"{t[:1]}."


def split_en_name(name: str) -> Tuple[str, str]:
    """
    朴素英文名拆分：支持 'Xi Zhang' / 'Zhang, Xi' 两种主流格式。
    返回 (given, family)；若无法判断，尽量按空格切并取最后一个为姓。
    """
    n = normalize_name(name)
    if "," in n:
        # 'zhang, xi'
        fam, giv = [x.strip() for x in n.split(",", 1)]
        return giv.title(), fam.title()
    parts = n.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]).title(), parts[-1].title()
    # 回退：全给名
    return n.title(), ""


def generate_variants(cn_name: str, pinyin_override: Optional[str] = None) -> Dict[int, List[str]]:
    """
    生成分优先级的姓名变体：P0(核心)/P1(常用缩写)/P2(扩展)/P3(低优先).
    仅用于**展示与宽召回**；真正匹配时会再做 normalize。
    """
    res: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}

    # P0：中英文最直接形式
    if cn_name:
        res[0].append(cn_name)

    pin = (pinyin_override or "").strip() or cn_to_pinyin_space(cn_name) or ""
    pin = _SPACES.sub(" ", pin).strip()
    if pin:
        # Xi Zhang / Zhang Xi / Zhang, Xi
        giv, fam = split_en_name(pin)  # 能容错倒序
        lf = f"{fam} {giv}".strip()
        fl = f"{giv} {fam}".strip()
        comma = f"{fam}, {giv}".strip(", ").strip()
        for s in (fl, lf, comma):
            if s and s not in res[0]:
                res[0].append(s)

        # P1：缩写（带点与不带点两版）
        if giv and fam:
            giv_first = _abbr_token(giv.split()[0])
            fam_first = _abbr_token(fam.split()[0])
            p1 = [
                f"{giv_first} {fam}", f"{fam_first} {giv}",
                f"{fam} {giv_first}", f"{fam}, {giv_first}",
                f"{giv_first}{fam_first}",  # 极简 'XZ'
                f"{giv[:1]} {fam}", f"{fam[:1]} {giv}",  # 不带点
            ]
            res[1].extend([_SPACES.sub(" ", s).strip() for s in p1])

        # P2：符号/连写扩展
        p2 = [
            fl.replace(" ", "-"), lf.replace(" ", "-"),
            fl.replace(" ", ""), lf.replace(" ", ""),
            fl.replace(" ", "."), lf.replace(" ", "."),
        ]
        res[2].extend(p2)

    # 去重
    for k in res:
        seen: Set[str] = set()
        uniq: List[str] = []
        for s in res[k]:
            if s and s.lower() not in seen:
                seen.add(s.lower()); uniq.append(s)
        res[k] = uniq
    return res


def all_variant_texts_for_match(cn_name: str, pinyin_override: Optional[str] = None) -> List[str]:
    """
    为“匹配”准备的扁平列表（全部小写/去标点），便于与作者列表做快速包含判断。
    """
    groups = generate_variants(cn_name, pinyin_override)
    flat = [x for _, arr in sorted(groups.items()) for x in arr]
    # 同时加入“first last”的互换（进一步稳健）
    extra: List[str] = []
    for v in flat:
        giv, fam = split_en_name(v)
        if giv and fam:
            extra.append(f"{giv} {fam}")
            extra.append(f"{fam} {giv}")
            extra.append(f"{fam}, {giv}")
    flat.extend(extra)

    # 标准化后去重
    normed: List[str] = []
    seen: Set[str] = set()
    for x in flat:
        n = compact_token(x)
        if n and n not in seen:
            seen.add(n); normed.append(n)
    return normed


def any_variant_match(authors: Iterable[str], variants_norm_tokens: Iterable[str]) -> bool:
    """
    判断：给定作者字符串列表（来自 openalex/crossref/arxiv），是否包含任一“姓名变体”。
    采用强归一 token 比较（仅字母数字），同时兼容 'Zhang, Xi' 与 'Xi Zhang'。
    """
    vt: Set[str] = set(variants_norm_tokens or [])
    if not authors or not vt:
        return False
    for a in authors:
        if not a:
            continue
        # 直接 token
        if compact_token(a) in vt:
            return True
        # 规范化 'fam, giv'
        giv, fam = split_en_name(a)
        if compact_token(f"{giv} {fam}") in vt:
            return True
        if compact_token(f"{fam} {giv}") in vt:
            return True
        if compact_token(f"{fam}, {giv}") in vt:
            return True
    return False
