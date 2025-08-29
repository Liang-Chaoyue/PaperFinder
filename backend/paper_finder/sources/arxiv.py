# paper_finder/sources/arxiv.py
from __future__ import annotations
import httpx
import xml.etree.ElementTree as ET
from datetime import date
from typing import List, Optional
from .base import PaperItem


def _parse_iso_date(s: str) -> Optional[date]:
    """arXiv ATOM: 形如 'YYYY-MM-DDTHH:MM:SSZ'，取前 10 位做日期。"""
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


class ArxivAdapter:
    source_name = "arxiv"
    base = "https://export.arxiv.org/api/query"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout



    from datetime import date
    from typing import List, Optional
    from .base import PaperItem

    ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    def _parse_iso_date(s: str) -> Optional[date]:
        if not s: return None
        try:
            return date.fromisoformat(s[:10])
        except Exception:
            return None

    class ArxivAdapter:
        source_name = "arxiv"
        base = "https://export.arxiv.org/api/query"

        def __init__(self, timeout: float = 15.0):
            self.timeout = timeout

        def search(self, query: str, hints: dict) -> List[PaperItem]:
            aff_kw = (hints.get("aff_kw") or "").strip()
            # ✅ 在全文里附带单位关键词（arXiv 没有独立的 affiliation 字段查询）
            q = f'(au:"{query}")'
            if aff_kw:
                q += f' AND all:"{aff_kw}"'

            params = {
                "search_query": q, "start": 0,
                "max_results": int(hints.get("max_results", 20)),
                "sortBy": "submittedDate", "sortOrder": "descending",
            }

            with httpx.Client(timeout=self.timeout, headers={"User-Agent": "PaperFinder/0.1"}) as cli:
                r = cli.get(self.base, params=params)
                r.raise_for_status()
                root = ET.fromstring(r.text)

            dr = hints.get("date_range") or {}
            sd = date.fromisoformat(dr["start"]) if dr.get("start") else None
            ed = date.fromisoformat(dr["end"]) if dr.get("end") else None

            items: List[PaperItem] = []
            for entry in root.findall("atom:entry", ARXIV_NS):
                title = (entry.findtext("atom:title", default="", namespaces=ARXIV_NS) or "").strip()

                published = entry.findtext("atom:published", default="", namespaces=ARXIV_NS) or ""
                updated = entry.findtext("atom:updated", default="", namespaces=ARXIV_NS) or ""
                pub_date = _parse_iso_date(published) or _parse_iso_date(updated)
                year = pub_date.year if pub_date else None

                url = entry.findtext("atom:id", default="", namespaces=ARXIV_NS) or ""
                pdf_url = ""
                for link in entry.findall("atom:link", ARXIV_NS):
                    if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                        pdf_url = link.attrib.get("href", "") or pdf_url

                authors, affs = [], []
                for a in entry.findall("atom:author", ARXIV_NS):
                    nm = a.findtext("atom:name", default="", namespaces=ARXIV_NS) or ""
                    if nm: authors.append(nm)
                    # ✅ 解析 arXiv 扩展命名空间里的 affiliation（不一定都有）
                    af = a.findtext("arxiv:affiliation", default="", namespaces=ARXIV_NS)
                    if af: affs.append(af)

                # 日期过滤
                if sd and pub_date and pub_date < sd: continue
                if ed and pub_date and pub_date > ed: continue

                # ✅ 本地单位过滤（若填写关键词）
                if aff_kw:
                    low = aff_kw.lower()
                    # 有 affs 时严格匹配；没有 affs 时不强制丢弃（因为我们在 query 已经做了 all: 约束）
                    if affs and not any(low in (x or "").lower() for x in affs):
                        continue

                arxiv_id = url.rsplit("/", 1)[-1] if url else ""
                items.append(PaperItem(
                    title=title, authors=authors, year=year, venue="arXiv",
                    doi=None, url=url, pdf_url=pdf_url, source=self.source_name,
                    ext_ids={"arxiv": arxiv_id}, affiliations=affs,
                ))
            return items

