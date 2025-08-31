import re
import httpx
from .base import PaperItem

class OpenAlexAdapter:
    source_name = "openalex"
    base = "https://api.openalex.org"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    # ---------- 工具：规范化人名做严格匹配 ----------
    @staticmethod
    def _norm(s: str) -> str:
        # 仅保留字母数字，移除空白/标点/点号/连字符，统一小写
        return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", s or "").lower()

    def _author_matches_variant(self, authors: list[str], variant: str) -> bool:
        target = self._norm(variant)
        for nm in authors or []:
            if self._norm(nm) == target:
                return True
        return False

    def _fetch(self, params: dict):
        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.get(f"{self.base}/works", params=params)
            r.raise_for_status()
            return r.json()

    def _parse_items(self, data: dict):
        items = []
        for w in data.get("results", []) or []:
            authors, affs = [], []
            for a in w.get("authorships", []) or []:
                nm = a.get("author", {}).get("display_name") or a.get("display_name") or ""
                if nm:
                    authors.append(nm)
                for inst in a.get("institutions") or []:
                    dn = inst.get("display_name")
                    if dn:
                        affs.append(dn)

            items.append(PaperItem(
                title=w.get("title", "") or "",
                authors=authors,
                year=w.get("publication_year"),
                venue=(w.get("host_venue") or {}).get("display_name", "") or "",
                doi=(w.get("doi") or "").replace("https://doi.org/", "") or None,
                url=w.get("primary_location", {}).get("landing_page_url", "") or
                    (w.get("primary_location", {}).get("source", {}) or {}).get("url", "") or "",
                pdf_url=w.get("primary_location", {}).get("pdf_url", "") or "",
                source=self.source_name,
                ext_ids={"openalex": w.get("id")},
                affiliations=affs,
            ))
        return items

    def search(self, query: str, hints: dict):
        """
        只使用：姓名变体 (query) + 单位关键词 (aff_kw) + 可选时间范围。
        1) 首选使用 OpenAlex filter 精确过滤作者名与机构名；
        2) 若接口不支持或返回空，回退到全文 search='"姓名变体" "单位"'，
           并在本地再次严格过滤（作者名精确匹配 + 单位包含）。
        """
        # 输入
        variant = (query or "").strip()
        dr = hints.get("date_range") or {}
        start = dr.get("start")
        end = dr.get("end")
        aff_kw = (hints.get("aff_kw") or "").strip()

        # ---------- 方案 A：filter 精确过滤 ----------
        params_a = {
            "per_page": 25,
        }
        filters = []

        # 作者显示名模糊搜索（针对作者字段，不影响题目）
        if variant:
            # OpenAlex 支持 authorships.author.display_name.search
            filters.append(f"authorships.author.display_name.search:{variant}")

        # 机构名过滤
        if aff_kw:
            # OpenAlex 支持 authorships.institutions.display_name.search
            filters.append(f"authorships.institutions.display_name.search:{aff_kw}")

        # 日期（OpenAlex 支持作为顶层 filter 也支持 from_/to_ 参数，使用 filter 更一致）
        if start:
            filters.append(f"from_publication_date:{start}")
        if end:
            filters.append(f"to_publication_date:{end}")

        if filters:
            params_a["filter"] = ",".join(filters)

        items = []
        used_fallback = False
        try:
            data = self._fetch(params_a)
            items = self._parse_items(data)
        except httpx.HTTPStatusError:
            # 例如 400（某些 filter 组合不被支持），走回退
            used_fallback = True

        # 如果 A 方案返回为空，也尝试回退
        if not items:
            used_fallback = True

        # ---------- 方案 B：回退到全文 search，但仍做本地严格过滤 ----------
        if used_fallback:
            params_b = {"per_page": 25}
            search_terms = [f"\"{variant}\""] if variant else []
            if aff_kw:
                search_terms.append(f"\"{aff_kw}\"")
            if search_terms:
                params_b["search"] = " ".join(search_terms)

            # 日期范围（保留）
            if start:
                params_b["from_publication_date"] = start
            if end:
                params_b["to_publication_date"] = end

            try:
                data_b = self._fetch(params_b)
                items = self._parse_items(data_b)
            except httpx.HTTPStatusError:
                items = []

            # 本地严格过滤：作者名必须与该姓名变体匹配；若提供了单位关键词，机构需包含
            if items:
                norm_aff = aff_kw.lower()
                filtered = []
                for it in items:
                    author_ok = self._author_matches_variant(it.authors, variant)
                    aff_ok = True
                    if aff_kw:
                        aff_ok = any(norm_aff in (x or "").lower() for x in (it.affiliations or []))
                    if author_ok and aff_ok:
                        filtered.append(it)
                items = filtered

        # 最终结果（若不是回退，也补一层轻量本地过滤以确保“只基于姓名变体+单位”）
        if not used_fallback and items:
            norm_aff = aff_kw.lower()
            strict = []
            for it in items:
                author_ok = self._author_matches_variant(it.authors, variant)
                aff_ok = True
                if aff_kw:
                    aff_ok = any(norm_aff in (x or "").lower() for x in (it.affiliations or []))
                if author_ok and aff_ok:
                    strict.append(it)
            items = strict

        return items
