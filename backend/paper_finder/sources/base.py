from typing import Iterable, Dict, Any, List, Protocol

class PaperItem(dict):
    """统一输出字段：
    title, authors(list[str]), year, venue, doi, url, pdf_url, source, ext_ids(dict), affiliations(list[str])
    """
    pass

class Adapter(Protocol):
    source_name: str
    def search(self, query: str, hints: Dict[str, Any]) -> Iterable[PaperItem]:
        ...
