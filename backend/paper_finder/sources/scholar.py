# paper_finder/sources/scholar.py
# -*- coding: utf-8 -*-

import os
import httpx
from .base import PaperItem

class ScholarAdapter:
    """
    通过 SerpAPI 查询 Google Scholar。
    - 若没有 SERPAPI_KEY，不抛异常，直接置为 disabled，并在 search 返回空列表。
    - 这样项目在未配置密钥时也能跑起来。
    """
    source_name = "scholar"
    base = "https://serpapi.com/search"

    def __init__(self, api_key: str | None = None, timeout: float = 20.0):
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        self.timeout = timeout
        self.enabled = bool(self.api_key)

    def search(self, query: str, hints: dict):
        if not self.enabled:
            # 不可用时静默返回空结果，避免整个站点启动失败
            return []

        params = {
            "engine": "google_scholar",
            "q": query,
            "num": 20,
            "api_key": self.api_key,
        }

        # 时间范围（尽量用 after/before；SerpAPI 会翻译成搜索操作符）
        dr = hints.get("date_range") or {}
        if dr.get("start"):
            params["as_ylo"] = dr["start"][:4]  # 年
        if dr.get("end"):
            params["as_yhi"] = dr["end"][:4]

        # 单位关键词（并入 q）
        aff_kw = (hints.get("aff_kw") or "").strip()
        if aff_kw:
            params["q"] = f'{query} "{aff_kw}"'

        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.get(self.base, params=params)
            r.raise_for_status()
            data = r.json()

        items = []
        for res in data.get("organic_results", []) or []:
            title = (res.get("title") or "").strip()
            link = (res.get("link") or "").strip()
            pubinfo = res.get("publication_info") or {}
            authors = []
            for a in pubinfo.get("authors") or []:
                nm = a.get("name")
                if nm:
                    authors.append(nm)
            venue = pubinfo.get("summary") or ""
            year = None
            # 从摘要中尽力抽一个年份
            if venue:
                import re
                m = re.search(r"(19|20)\d{2}", venue)
                if m:
                    year = int(m.group(0))

            items.append(PaperItem(
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                doi=None,
                url=link,
                pdf_url="",
                source=self.source_name,
                ext_ids={"scholar_id": res.get("result_id")},
                affiliations=[],
            ))
        return items
