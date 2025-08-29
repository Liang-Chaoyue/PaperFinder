# paper_finder/services/storage.py
from __future__ import annotations
from typing import Iterable, Dict, Tuple, List, Optional
from django.db import transaction

from ..models import Paper
from ..utils.names import compact_token


def _key_for_dedupe(item) -> Tuple[str, Optional[int], str]:
    """
    用于批内去重与数据库查重的 key：
      - 优先 DOI（小写）；
      - 否则 (title_token, year, source)
    """
    doi = (item.doi or "").strip().lower()
    if doi:
        return ("doi", None, doi)
    title_token = compact_token(item.title or "")
    return ("tysource", item.year, f"{title_token}|{item.source}")


def dedupe_in_memory(items: Iterable) -> List:
    """
    批次内去重（避免同一来源/多来源重复返回同一条）。
    """
    seen: Dict[Tuple[str, Optional[int], str], int] = {}
    uniq: List = []
    for it in items:
        k = _key_for_dedupe(it)
        if k not in seen:
            seen[k] = 1
            uniq.append(it)
    return uniq


@transaction.atomic
def save_items(job_id: str, items: Iterable, default_state: str = "pending") -> int:
    """
    把 PaperItem 列表落库到 Paper 表：
      - 用 DOI 做唯一键；无 DOI 时按 (title_token, year, source) 兜底；
      - 如已存在则更新 url/venue/year/source，并覆盖 task_ref（指向**最近一次**所属 job）；
      - score 这里不参与（你的需求是“不要评分”）。
    返回：入库/更新的条数。
    """
    count = 0
    for it in items:
        doi = (it.doi or "").strip().lower() or None

        if doi:
            obj, created = Paper.objects.update_or_create(
                doi=doi,
                defaults=dict(
                    title=it.title or "",
                    year=it.year,
                    venue=it.venue or "",
                    url=it.url or "",
                    source=it.source or "",
                    task_ref=job_id,
                    state=getattr(it, "state", default_state) or default_state,
                    score=0.0,
                ),
            )
            count += 1
            continue

        # 无 DOI：用 (title_token, year, source) 查重
        title_token = compact_token(it.title or "")
        found = Paper.objects.filter(
            year=it.year,
            source=(it.source or ""),
            # 简单标题 token 匹配（避免同题大小写/符号差异）
            title__iregex=rf"^{re_escape_token(title_token)}$"
        ).first()

        if found:
            # 更新
            found.title = it.title or found.title
            found.venue = it.venue or found.venue
            found.url = it.url or found.url
            found.task_ref = job_id
            found.state = getattr(it, "state", default_state) or default_state
            found.score = 0.0
            found.save(update_fields=["title", "venue", "url", "task_ref", "state", "score"])
            count += 1
        else:
            # 新建
            Paper.objects.create(
                title=it.title or "",
                year=it.year,
                venue=it.venue or "",
                doi=None,
                url=it.url or "",
                source=it.source or "",
                score=0.0,
                state=getattr(it, "state", default_state) or default_state,
                task_ref=job_id,
            )
            count += 1
    return count


def re_escape_token(tok: str) -> str:
    """
    把 compact_token 结果转回一个安全的正则：这里只包含 a-z0-9，本质上等价于精确匹配。
    """
    # compact_token 只有小写字母数字，这里防御性转义
    import re
    return re.escape(tok)
