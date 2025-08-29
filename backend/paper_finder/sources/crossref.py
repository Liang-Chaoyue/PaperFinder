import httpx
from .base import PaperItem

class CrossrefAdapter:
    source_name = "crossref"
    base = "https://api.crossref.org"

    def __init__(self, timeout: float = 15.0, mailto: str = "example@example.com"):
        self.timeout = timeout
        self.mailto = mailto

    def search(self, query: str, hints: dict):
        params = {"query.author": query, "rows": 20, "mailto": self.mailto}

        # 日期
        dr = hints.get("date_range") or {}
        filt = []
        if dr.get("start"): filt.append(f"from-pub-date:{dr['start']}")
        if dr.get("end"):   filt.append(f"until-pub-date:{dr['end']}")
        if filt: params["filter"] = ",".join(filt)

        # ✅ 单位关键词：官方支持
        aff_kw = (hints.get("aff_kw") or "").strip()
        if aff_kw:
            params["query.affiliation"] = aff_kw

        with httpx.Client(timeout=self.timeout,
                          headers={"User-Agent": f"PaperFinder/0.1 (mailto:{self.mailto})"}) as cli:
            r = cli.get(f"{self.base}/works", params=params)
            r.raise_for_status()
            data = r.json()

        items = []
        for w in (data.get("message") or {}).get("items", []):
            title = " ".join(w.get("title") or []) or ""
            authors, affs = [], []
            for a in w.get("author") or []:
                nm = " ".join(filter(None, [a.get("given"), a.get("family")]))
                if nm: authors.append(nm)
                for af in a.get("affiliation") or []:
                    if af.get("name"): affs.append(af["name"])

            # ✅ 本地兜底过滤（以防上游召回宽松）
            if aff_kw:
                low = aff_kw.lower()
                if affs and not any(low in (x or "").lower() for x in affs):
                    continue

            items.append(PaperItem(
                title=title,
                authors=authors,
                year=(w.get("published-print") or w.get("issued") or {}).get("date-parts", [[None]])[0][0],
                venue=(w.get("container-title") or [""])[0],
                doi=(w.get("DOI") or None),
                url=w.get("URL", ""),
                pdf_url="",
                source=self.source_name,
                ext_ids={"crossref": w.get("DOI")},
                affiliations=affs,
            ))
        return items

