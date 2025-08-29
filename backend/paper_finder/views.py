import uuid, time, csv
from typing import Dict, List, Tuple
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse
from django.utils.encoding import smart_str
from django.db.models import Count

from .services.matching import keep_paper_boolean, aff_hits
from .services.storage import dedupe_in_memory, save_items
from .utils.names import generate_variants, all_variant_texts_for_match

from .forms import SearchForm, PaperFilterForm
from .models import SearchJob, Paper
from .sources.openalex import OpenAlexAdapter
from .sources.crossref import CrossrefAdapter
from .sources.arxiv import ArxivAdapter

# Celery 可选
try:
    from .tasks import run_job_async
    HAS_CELERY = True
except Exception:
    HAS_CELERY = False


# --- 适配器注册 ---
ADAPTERS = {
    "openalex": OpenAlexAdapter(),
    "crossref": CrossrefAdapter(mailto="youremail@example.com"),
    "arxiv": ArxivAdapter(),
}


# === 内部工具：把姓名变体结果统一成 [(priority:int, text:str)] ===
def _normalize_variants(raw) -> List[Tuple[int, str]]:
    pairs: List[Tuple[int, str]] = []
    if isinstance(raw, dict):
        # 形如 {0:[...],1:[...]}
        for pri, items in raw.items():
            p = int(pri) if str(pri).isdigit() else 1
            for t in items or []:
                t = (t or "").strip()
                if t:
                    pairs.append((p, t))
    elif isinstance(raw, list):
        if raw and hasattr(raw[0], "priority"):
            # 老版对象：有 .priority / .text
            for v in raw:
                p = int(getattr(v, "priority", 1))
                t = getattr(v, "text", str(v)).strip()
                if t:
                    pairs.append((p, t))
        else:
            # 简单字符串列表
            for t in raw:
                t = (t or "").strip()
                if t:
                    pairs.append((1, t))
    return pairs


# === 内部：将一个 item 写入 Paper（按 job_id 去重更新）===
def upsert_paper(item: dict, task_ref: str, hints: dict):
    """
    期望 item 字段（适配器应已规范化）：
    title:str, authors:list[str], venue:str, year:int|None, month:int|None,
    doi:str|None, url:str|None, source:str, score:float|None
    """
    title = (item.get("title") or "").strip()
    source = (item.get("source") or "").strip() or "unknown"
    doi = (item.get("doi") or "").strip().lower() or None
    url = (item.get("url") or "").strip() or None
    year = item.get("year")
    month = item.get("month")
    authors = item.get("authors") or []
    venue = item.get("venue") or ""
    score = item.get("score", 0.0)

    # 兜底格式化
    try:
        month = int(month) if month not in (None, "") else None
    except Exception:
        month = None
    try:
        year = int(year) if year not in (None, "") else None
    except Exception:
        year = None

    # 查重键：优先 job+doi；否则 job+title+source
    if doi:
        lookup = {"task_ref": task_ref, "doi": doi}
    else:
        lookup = {"task_ref": task_ref, "title": title, "source": source}

    defaults = {
        "title": title,
        "authors": authors,
        "venue": venue,
        "year": year,
        "month": month,
        "doi": doi,
        "url": url,
        "source": source,
        "score": score or 0.0,
    }
    Paper.objects.update_or_create(defaults=defaults, **lookup)


def search_page(request):
    if request.method == "POST":
        form = SearchForm(request.POST)
        action = request.POST.get("action", "search")  # ✅ 提前定义，避免 NameError
        if form.is_valid():
            # 读取表单
            name   = form.cleaned_data["name"].strip()
            pinyin = (form.cleaned_data["pinyin"] or "").strip() or None
            sources = form.cleaned_data["sources"]
            sd = form.cleaned_data.get("start_date")
            ed = form.cleaned_data.get("end_date")
            aff_kw = (form.cleaned_data.get("affiliation") or "").strip()

            # 组装 hints（历史/导出/适配器都用它）
            hints: Dict = {
                "sources": sources,
                "query_name": name,
                "pinyin": pinyin,
                "aff_kw": aff_kw or None,
                "date_range": {
                    "start": sd.isoformat() if sd else None,
                    "end":   ed.isoformat() if ed else None,
                },
            }

            # ✅ 预览姓名变体
            if action == "preview":
                raw = generate_variants(name, pinyin_override=pinyin)
                pairs = _normalize_variants(raw)
                # 分组供模板展示
                groups = defaultdict(list)
                for pri, text in pairs:
                    groups[int(pri)].append(text)
                variant_count = len(pairs)
                return render(request, "paper_finder/search.html", {
                    "form": form,
                    "variant_count": variant_count,
                    "variant_groups": [
                        (0, groups.get(0, [])),
                        (1, groups.get(1, [])),
                        (2, groups.get(2, [])),
                        (3, groups.get(3, [])),
                    ],
                })

            # ✅ 发起检索
            run_sync = form.cleaned_data.get("run_sync")
            job_id = uuid.uuid4().hex[:16]
            SearchJob.objects.create(job_id=job_id, hints=hints, status="running", progress=0.0)
            request.session["last_job_id"] = job_id  # 记录最近一次

            if run_sync or not HAS_CELERY:
                _run_search_once(job_id, name, pinyin, hints, max_variants=8, pause=0.6)
                return redirect("paper_finder:job_status", job_id=job_id)
            else:
                run_job_async.delay(job_id, name, hints, pinyin_override=pinyin)
                return redirect("paper_finder:job_status", job_id=job_id)
        # 表单校验失败 → 回显错误
        return render(request, "paper_finder/search.html", {"form": form})
    else:
        form = SearchForm()
        return render(request, "paper_finder/search.html", {"form": form})


def job_status(request, job_id: str):
    job = get_object_or_404(SearchJob, pk=job_id)
    papers = Paper.objects.filter(task_ref=job_id).order_by("-score","-year")[:50]
    auto_refresh = (job.status == "running")
    return render(request, "paper_finder/job_status.html", {
        "job": job, "papers": papers, "auto_refresh": auto_refresh
    })


def paper_list(request):
    job_id = request.GET.get("job_id")

    # 支持多任务对比：jobs=id1,id2 或 ?jobs=id1&jobs=id2
    jobs_param = request.GET.getlist("jobs") or request.GET.get("jobs")
    job_ids = []
    if isinstance(jobs_param, list):
        job_ids = jobs_param
    elif isinstance(jobs_param, str) and jobs_param.strip():
        job_ids = [x.strip() for x in jobs_param.split(",") if x.strip()]

    # --- 兜底：没有任何参数时的处理 ---
    if not job_id and not job_ids:
        # 1) 优先跳转到最近一次任务（存于 session）
        last = request.session.get("last_job_id")
        if last:
            return redirect(f"{reverse('paper_finder:paper_list')}?job_id={last}")

        # 2) 没有 session，就查数据库里最新的一条任务
        latest = SearchJob.objects.order_by("-created_at").first()
        if latest:
            return redirect(f"{reverse('paper_finder:paper_list')}?job_id={latest.job_id}")

        # 3) 仍然没有任何任务 → 展示选择页（空则引导去发起）
        recent_jobs = SearchJob.objects.order_by("-created_at")[:50]
        if not recent_jobs:
            return render(request, "paper_finder/empty_list.html", {
                "tip": "暂无历史结果，请先发起一次检索。"
            })
        return render(request, "paper_finder/paper_list_landing.html", {
            "recent_jobs": recent_jobs
        })

    # --- 有参数时：正常查询 ---
    qs = Paper.objects.all().order_by("-score", "-year", "-id")
    if job_id:
        qs = qs.filter(task_ref=job_id)
    if job_ids:
        qs = qs.filter(task_ref__in=job_ids)

    form = PaperFilterForm(request.GET or None)
    if form.is_valid():
        q = form.cleaned_data.get("q")
        state = form.cleaned_data.get("state")
        source = form.cleaned_data.get("source")
        y1 = form.cleaned_data.get("year_from")
        y2 = form.cleaned_data.get("year_to")
        if q: qs = qs.filter(title__icontains=q)
        if state: qs = qs.filter(state=state)
        if source: qs = qs.filter(source=source)
        if y1: qs = qs.filter(year__gte=y1)
        if y2: qs = qs.filter(year__lte=y2)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    # 供页头的“任务选择框”使用
    recent_jobs = SearchJob.objects.order_by("-created_at")[:100]

    return render(request, "paper_finder/paper_list.html", {
        "form": form,
        "page_obj": page_obj,
        "job_id": job_id,
        "papers": page_obj.object_list,
        "job_ids": ",".join(job_ids) if job_ids else "",
        "recent_jobs": recent_jobs,
    })


def job_history(request):
    # 基础列表（可按时间/关键词过滤）
    qs = SearchJob.objects.all().order_by("-created_at")

    # 轻量过滤（可选）
    q = request.GET.get("q", "").strip()
    if q:
        # 在 hints 的 query_name / aff_kw 上做包含匹配
        qs = qs.filter(hints__query_name__icontains=q) | qs.filter(hints__aff_kw__icontains=q)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    # 统计每个 job 的结果条数（总数与 confirmed 数）
    from django.db.models import Q  # 局部导入，避免全局命名污染
    agg = (
        Paper.objects
        .values("task_ref")
        .annotate(
            total=Count("id"),
            confirmed=Count("id", filter=Q(state="confirmed")),
        )
    )
    stat_map = {a["task_ref"]: (a["total"], a["confirmed"]) for a in agg}

    # 给分页内的每个 job 附上计数
    for job in page_obj.object_list:
        total, confirmed = stat_map.get(job.job_id, (0, 0))
        job.paper_total = total
        job.paper_confirmed = confirmed

    # 记录最近 job
    if page_obj.object_list:
        request.session["last_job_id"] = page_obj.object_list[0].job_id

    return render(request, "paper_finder/job_history.html", {
        "page_obj": page_obj,
        "q": q,
    })


ALLOWED_STATES = {"pending", "confirmed", "rejected"}


@require_POST
def mark_paper(request, pk: int):
    state = (request.POST.get("state") or "").strip().lower()
    if state not in ALLOWED_STATES:
        return HttpResponseBadRequest("invalid state")

    p = get_object_or_404(Paper, pk=pk)
    p.state = state
    p.save(update_fields=["state"])

    # 优先回到提交前的页面
    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)

    # 其次带着 job_id 回到结果列表
    job_id = request.POST.get("job_id") or p.task_ref
    if job_id:
        return redirect(f"{reverse('paper_finder:paper_list')}?job_id={job_id}")

    # 最后兜底
    return redirect("paper_finder:paper_list")


def export_csv(request):
    job_id = request.GET.get("job_id")
    state = request.GET.get("state")
    qs = Paper.objects.all()
    if job_id: qs = qs.filter(task_ref=job_id)
    if state: qs = qs.filter(state=state)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="papers_{job_id or "all"}.csv"'
    w = csv.writer(resp)
    w.writerow(["Title","Year","Venue","DOI","URL","Source","Score","State","Task"])
    for p in qs.iterator(chunk_size=1000):
        w.writerow([p.title, p.year or "", p.venue, p.doi or "", p.url, p.source, f"{p.score:.2f}", p.state, p.task_ref])
    return resp


# --- 内部：同步执行（调试/无 Celery）
def _run_search_once(job_id: str, name: str, pinyin_override: str | None, hints: dict, max_variants=8, pause=0.6):
    raw_variants = generate_variants(name, pinyin_override=pinyin_override)
    pairs = _normalize_variants(raw_variants)
    # 仅取 P<=2 的变体，并限制数量
    pairs.sort(key=lambda x: x[0])
    variants: List[str] = [t for p, t in pairs if p <= 2][:max_variants]

    job = SearchJob.objects.get(pk=job_id)
    sources = hints.get("sources", ["openalex"])
    total = len(variants) * len(sources)
    done = 0

    for v in variants:
        for src in sources:
            adp = ADAPTERS.get(src)
            if not adp:
                continue
            try:
                items = adp.search(v, hints)
            except Exception:
                items = []

            for it in items:
                # 可按需调用 keep_paper_boolean/aff_hits 做筛选
                upsert_paper(it, task_ref=job_id, hints=hints)

            done += 1
            job.progress = round(done / max(1, total), 3)
            job.save(update_fields=["progress"])
            time.sleep(pause)

    job.status = "done"
    job.save(update_fields=["status"])


@require_GET
def export_job_csv(request):
    job_id = request.GET.get("job_id")
    if not job_id:
        return HttpResponse("缺少 job_id", status=400)

    qs = Paper.objects.filter(task_ref=job_id).order_by("-year", "-month", "title")

    resp = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="{job_id}.csv"'

    writer = csv.writer(resp)
    writer.writerow(["论文题目", "论文全体作者", "学术会议或刊物名称", "出版年份", "出版月", "来源", "DOI", "URL"])
    for p in qs:
        authors_str = ", ".join(p.authors or []) if isinstance(p.authors, list) else (p.authors or "")
        writer.writerow([
            smart_str(p.title or ""),
            smart_str(authors_str),
            smart_str(p.venue or ""),
            p.year or "",
            p.month or "",
            p.source or "",
            smart_str(p.doi or ""),
            smart_str(p.url or ""),
        ])
    return resp
