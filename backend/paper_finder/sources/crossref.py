import httpx
from .base import PaperItem


class CrossrefAdapter:
    source_name = "crossref"
    base = "https://api.crossref.org"   # ✅ 直接用 https

    def __init__(self, timeout: float = 15.0, mailto: str = "example@example.com"):
        self.timeout = timeout
        self.mailto = mailto

    def search(self, query: str, hints: dict):
        params = {"query.author": query, "rows": 20, "mailto": self.mailto}

        # 日期范围
        dr = hints.get("date_range") or {}
        filt = []
        if dr.get("start"):
            filt.append(f"from-pub-date:{dr['start']}")
        if dr.get("end"):
            filt.append(f"until-pub-date:{dr['end']}")
        if filt:
            params["filter"] = ",".join(filt)

        # ✅ 单位关键词：Crossref 支持 affiliation 检索
        aff_kw = (hints.get("aff_kw") or "").strip()
        if aff_kw:
            params["query.affiliation"] = aff_kw

        # 🔹 网络请求
        with httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": f"PaperFinder/0.1 (mailto:{self.mailto})"},
            follow_redirects=True,   # ✅ 自动跟随 301
            verify=False             # ✅ 忽略 SSL 证书问题
        ) as cli:
            r = cli.get(f"{self.base}/works", params=params)
            r.raise_for_status()
            data = r.json()

        # 🔹 获取姓名变体（全部转小写去空格）
        variants = [v.lower().replace(" ", "") for v in hints.get("name_variants", [])]

        items = []
        for w in (data.get("message") or {}).get("items", []):
            title = " ".join(w.get("title") or []) or ""
            authors, affs = [], []

            for a in w.get("author") or []:
                nm = " ".join(filter(None, [a.get("given"), a.get("family")]))
                if nm:
                    authors.append(nm)
                for af in a.get("affiliation") or []:
                    if af.get("name"):
                        affs.append(af["name"])

            # ✅ 单位兜底过滤（API 可能召回宽松）
            if aff_kw:
                low = aff_kw.lower()
                if affs and not any(low in (x or "").lower() for x in affs):
                    continue

            # ✅ 姓名变体过滤：必须匹配至少一个变体
            if variants:
                author_keys = ["".join(a.lower().split()) for a in authors]
                if not any(v in ak or ak in v for ak in author_keys for v in variants):
                    continue

            items.append(
                PaperItem(
                    title=title,
                    authors=authors,
                    year=(w.get("published-print") or w.get("issued") or {}).get(
                        "date-parts", [[None]]
                    )[0][0],
                    venue=(w.get("container-title") or [""])[0],
                    doi=(w.get("DOI") or None),
                    url=w.get("URL", ""),
                    pdf_url="",
                    source=self.source_name,
                    ext_ids={"crossref": w.get("DOI")},
                    affiliations=affs,
                )
            )

        return items
