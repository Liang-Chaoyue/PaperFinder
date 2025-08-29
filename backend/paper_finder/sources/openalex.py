import httpx
from .base import PaperItem

class OpenAlexAdapter:
    source_name = "openalex"
    base = "https://api.openalex.org"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def search(self, query: str, hints: dict):
        params = {"search": query, "per_page": 25}

        # 日期范围
        dr = hints.get("date_range") or {}
        if dr.get("start"):
            params["from_publication_date"] = dr["start"]
        if dr.get("end"):
            params["to_publication_date"] = dr["end"]

        # ✅ 单位关键词参与全文检索（增强召回）
        aff_kw = (hints.get("aff_kw") or "").strip()
        if aff_kw:
            params["search"] = f'{query} {aff_kw}'

        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.get(f"{self.base}/works", params=params)
            r.raise_for_status()
            data = r.json()

        items = []
        for w in data.get("results", []):
            authors, affs = [], []
            for a in w.get("authorships", []) or []:
                nm = a.get("author", {}).get("display_name") or a.get("display_name") or ""
                if nm: authors.append(nm)
                for inst in a.get("institutions") or []:
                    dn = inst.get("display_name")
                    if dn: affs.append(dn)

            # ✅ 本地过滤：若提供单位关键词，仅保留包含该关键词的条目
            if aff_kw:
                low = aff_kw.lower()
                if not any(low in (x or "").lower() for x in affs):
                    continue

            items.append(PaperItem(
                title=w.get("title", ""),
                authors=authors,
                year=w.get("publication_year"),
                venue=(w.get("host_venue") or {}).get("display_name", ""),
                doi=(w.get("doi") or "").replace("https://doi.org/", "") or None,
                url=w.get("primary_location", {}).get("landing_page_url", "") or
                    w.get("primary_location", {}).get("source", {}).get("url", ""),
                pdf_url=w.get("primary_location", {}).get("pdf_url", "") or "",
                source=self.source_name,
                ext_ids={"openalex": w.get("id")},
                affiliations=affs,
            ))
        return items
