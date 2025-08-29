# paper_finder/services/matching.py
from __future__ import annotations
from typing import Iterable, List, Optional

from ..utils.names import normalize_name, any_variant_match


def aff_hits(aff_list: Optional[Iterable[str]], aff_kw: Optional[str]) -> bool:
    """
    单位命中：若未填写 aff_kw 则视为通过；填写时需在任一 affiliation 中出现（大小写/符号不敏感）。
    """
    if not aff_kw:
        return True
    key = normalize_name(aff_kw)
    for a in (aff_list or []):
        if key in normalize_name(a or ""):
            return True
    return False


def keep_paper_boolean(
    item,                       # adapters.base.PaperItem（含 authors、affiliations 等）
    variants_norm_tokens: List[str],
    aff_kw: Optional[str],
) -> bool:
    """
    纯布尔判定：是否保留该条目。
    规则：
      1) 作者中至少一个能与姓名变体匹配；
      2) 若提供了单位关键词，则在条目的 affiliations 里也需命中（arXiv 如果没提供 affs，会在查询时已做 all:"kw" 约束）。
    """
    if not any_variant_match(item.authors or [], variants_norm_tokens):
        return False

    if not aff_hits(item.affiliations or [], aff_kw):
        return False

    return True
